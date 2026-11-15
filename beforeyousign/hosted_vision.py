"""SmolVLM2 hosted inference over ALL authorized listing images.

The model itself is hosted on a dedicated GPU endpoint (vLLM compatible),
not inside Redis/Postgres. This backend only fetches existing listing images,
batches them for bounded GPU memory, combines the evidence into one bilingual
summary, and stores the result in Redis. No paid listing-provider requests occur.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlsplit
import base64
import json
import logging
import math
import os
import re
from typing import Any, Callable

from PIL import Image, ImageOps
import requests

LOG = logging.getLogger('beforeyousign.hosted_vision')
MODEL_NAME = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
MAX_PHOTOS = 100
BATCH_SIZE = 4
PROMPT_VERSION = '2'

class VisionError(Exception):
    """Safe, user-facing failure. Never return GPU credentials or image URLs."""


def safe_photo_urls(record: dict[str, Any]) -> list[str]:
    """Accept every available image up to a high but bounded safety ceiling."""
    from beforeyousign.report_services import _image_url
    seen: set[str] = set()
    result: list[str] = []
    for item in (record.get('photo_urls') or [])[:MAX_PHOTOS]:
        clean = _image_url(item)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def cache_key(listing_id: str, urls: list[str]) -> str:
    """Stable across regenerated signed photo URLs when image paths remain same."""
    paths = '|'.join(urlsplit(u).path for u in urls)
    digest = sha256((PROMPT_VERSION + '|' + paths).encode('utf-8')).hexdigest()[:24]
    return f'bys:vision-hosted:v{PROMPT_VERSION}:{listing_id}:{digest}'


def prepare_jpeg(source: bytes) -> bytes:
    if not 1000 <= len(source) <= 5_000_000:
        raise ValueError('Invalid image size')
    with Image.open(BytesIO(source)) as src:
        if src.width * src.height > 24_000_000:
            raise ValueError('Excessive image dimensions')
        image = ImageOps.exif_transpose(src).convert('RGB')
        image.thumbnail((768, 768))
        with BytesIO() as buffer:
            image.save(buffer, format='JPEG', quality=75, optimize=True)
            result = buffer.getvalue()
    if not 1000 <= len(result) <= 1_500_000:
        raise ValueError('Invalid normalized image size')
    return result


def model_host_configured(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    endpoint = env.get('BYS_VISION_API_URL', '')
    key = env.get('BYS_VISION_API_TOKEN', '')
    if not endpoint.startswith('https://') or not key:
        return False
    p = urlsplit(endpoint)
    return (bool(p.hostname) and not p.username and not p.password and not p.fragment
            and p.port in (None, 443) and p.path.rstrip('/').endswith('/v1/chat/completions'))


def host_chat(content: list[dict[str, Any]], *, env: dict[str, str] | None = None,
              post: Callable[..., Any] | None = None, tokens: int = 350) -> str:
    """Call only the operator-configured HTTPS GPU endpoint. No redirects."""
    env = os.environ if env is None else env
    if not model_host_configured(env):
        raise VisionError('The hosted SmolVLM2 model is not configured.')
    endpoint = env['BYS_VISION_API_URL']
    # This is an operator-controlled destination, never a browser-supplied URL.
    try:
        response = (post or requests.post)(
            endpoint,
            headers={'Authorization': 'Bearer ' + env['BYS_VISION_API_TOKEN'],
                     'Content-Type': 'application/json'},
            json={'model': env.get('BYS_VISION_MODEL') or MODEL_NAME,
                  'messages': [{'role': 'user', 'content': content}],
                  'max_tokens': tokens, 'temperature': 0.1},
            timeout=(6, 130), allow_redirects=False,
        )
        if response.status_code != 200:
            LOG.warning('Hosted vision request failed: http_status=%s', response.status_code)
            raise VisionError('Hosted vision temporarily unavailable (HTTP ' + str(int(response.status_code)) + ').')
        body = response.json()
        output = body['choices'][0]['message']['content']
        if not isinstance(output, str) or not output.strip() or len(output) > 14000:
            raise ValueError('Empty or oversized vision response')
        return output.strip()
    except VisionError:
        raise
    except requests.Timeout as exc:
        raise VisionError('Hosted image analysis timed out.') from exc
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        LOG.warning('Hosted vision response failed: kind=%s', type(exc).__name__)
        raise VisionError('The hosted model could not produce a valid response.') from exc


def _caption_prompt(photo_count: int) -> str:
    return (
        f'These are {photo_count} advertising images from ONE rental property. '
        'Write a concise factual inventory of their VISIBLE evidence only: rooms shown, '
        'finishes, furniture, windows, light sources and any obvious wear, stains or damage. '
        'Group observations together; do not repeat or write photo-by-photo reports. '
        'Do not assert hidden defects, mold, leaks, structural safety, legal compliance, '
        'noise levels, exact dimensions, actual natural light or a neighborhood score. '
        'If nothing concerning is visible, say no obvious issues were spotted in these photographs. '
        'Do not invent rooms or features. Reply in English, at most 170 words.'
    )


def _final_prompt(notes: list[str], analyzed: int, total: int) -> str:
    joined = '\n--- BATCH ---\n'.join(notes)
    return (
        'You are writing ONE evidence-conscious report for a renter. '
        f'Exactly {analyzed} of {total} available advertisement photos were inspected. '
        'Below are factual notes from image batches. The notes are evidence, not proof of hidden conditions. '
        'Combine all notes without redundancy. Do NOT give per-image or per-batch summaries. '
        'Do not invent features. Include only claims actually supported by the notes. '
        'Avoid declaring mold or structural safety. Provide a SINGLE short report in Spanish and English. '
        'Respond as JSON ONLY, keys: summary_es, summary_en, '
        'visible_strengths_es, visible_strengths_en, '
        'visible_concerns_es, visible_concerns_en, '
        'landlord_questions_es, landlord_questions_en. '
        'The summary values are short paragraphs (2-4 sentences); each remaining key is '
        'an array of up to 5 brief strings. If evidence is missing use an empty array. '
        'Do not include markdown. The Spanish and English versions must describe the same observations. '
        'NOTES:\n' + joined[:18000]
    )


def _parse_summary(output: str, *, analyzed: int, total: int) -> dict[str, Any]:
    """Fail visibly when a small model cannot follow structured-output instructions."""
    candidate = output.strip()
    if candidate.startswith('```'):
        candidate = re.sub(r'^```(?:json)?\s*|\s*```$', '', candidate, flags=re.I)
    begin, end = candidate.find('{'), candidate.rfind('}')
    if begin >= 0 and end > begin:
        candidate = candidate[begin:end+1]
    try:
        obj = json.loads(candidate)
    except (ValueError, TypeError):
        raise VisionError('The model returned an incomplete overall report; no findings were published.') from None
    if not isinstance(obj, dict):
        raise VisionError('The model returned an invalid overall report.')
    summary_es = obj.get('summary_es')
    summary_en = obj.get('summary_en')
    if not isinstance(summary_es, str) or not summary_es.strip() or not isinstance(summary_en, str) or not summary_en.strip():
        raise VisionError('The model could not prepare both report languages.')
    result: dict[str, Any] = {'status': 'completed' if analyzed == total else 'partial',
                              'model': MODEL_NAME, 'photos_available': total,
                              'photos_analyzed': analyzed, 'summary_es': summary_es.strip()[:1600],
                              'summary_en': summary_en.strip()[:1600]}
    for suffix in ('es', 'en'):
        for field in ('visible_strengths', 'visible_concerns', 'landlord_questions'):
            raw = obj.get(f'{field}_{suffix}', [])
            if not isinstance(raw, list):
                raw = []
            result[f'{field}_{suffix}'] = [item.strip()[:320] for item in raw[:5]
                                            if isinstance(item, str) and item.strip()]
    return result


def analyze_listing_images(record: dict[str, Any], *, env: dict[str, str] | None = None,
                           get_image: Callable[[str], bytes] | None = None,
                           send: Callable[..., str] | None = None) -> dict[str, Any]:
    """Inspect every available photo in 4-photo batches and return ONE report.

    A missing/broken photo is counted as unavailable; never pretend it was seen.
    No OpenData lookup happens here, and original pixels are not retained.
    """
    urls = safe_photo_urls(record)
    if not urls:
        raise VisionError('The listing provider has no accessible photo URLs.')
    if not model_host_configured(env):
        raise VisionError('The hosted SmolVLM2 model is not configured.')
    from beforeyousign.report_services import fetch_listing_image
    fetch = get_image or fetch_listing_image
    completion = send or host_chat
    notes: list[str] = []
    analyzed = 0
    processed = 0
    total = len(urls)
    for offset in range(0, total, BATCH_SIZE):
        batch = urls[offset:offset+BATCH_SIZE]
        content: list[dict[str, Any]] = []
        for url in batch:
            processed += 1
            try:
                photo = prepare_jpeg(fetch(url))
            except (OSError, ValueError, requests.RequestException):
                continue
            content.append({'type': 'image_url',
                            'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(photo).decode('ascii')}})
        if not content:
            continue
        analyzed += len(content)
        content.append({'type': 'text', 'text': _caption_prompt(len(content))})
        notes.append(completion(content, env=env, tokens=260))
    if analyzed == 0:
        raise VisionError('The listing images were inaccessible; no visual findings were produced.')
    prompt = _final_prompt(notes, analyzed, total)
    combined = completion([{'type':'text', 'text':prompt}], env=env, tokens=620)
    return _parse_summary(combined, analyzed=analyzed, total=total)