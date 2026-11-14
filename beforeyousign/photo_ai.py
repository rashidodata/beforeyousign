"""Optional multimodal inspection of visible attributes in rental photos."""
from __future__ import annotations
import base64
import io
import json
from typing import Any
from PIL import Image, ImageOps

SYSTEM_PROMPT = """You are an evidence-conscious rental-viewing assistant, NOT a surveyor, architect,
or building inspector. Assess only details visible in attached property listing photos.
Do not infer safety, legal compliance, soundproofing, structural integrity, hidden humidity,
energy efficiency, exact dimensions, mold, neighborhood crime, or natural daylight from
unverifiable clues. If a detail cannot be verified, say so. Do not identify people.
Respond with a single JSON object with the following keys:
summary (string), visible_strengths (array of objects with finding, evidence_photo),
visible_concerns (same structure), landlord_questions (array of strings),
not_verifiable_from_photos (array of strings). Mention visible items with neutral language
and refer to photos by index. No invented measurements or objective property scores.
Use concise, natural English. No Markdown in JSON."""


def prepare_photo(data: bytes, max_px: int = 1400) -> str:
    if len(data) > 15_000_000:
        raise ValueError('Photo larger than 15 MB. Please resize it.')
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((max_px, max_px))
        out = io.BytesIO()
        im.save(out, format='JPEG', quality=79, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode('ascii')


def inspect_photos(images: list[bytes], api_key: str, context: str = '') -> dict[str, Any]:
    if not api_key:
        raise ValueError('An OpenAI API key is needed for photo analysis.')
    if not 1 <= len(images) <= 8:
        raise ValueError('Upload between one and eight listing photos.')
    from openai import OpenAI
    content: list[dict[str, Any]] = [{'type': 'text', 'text': (
        f'Analyze these {len(images)} photos of a potential rental. Context (unverified user text): '
        f'{context[:1000]}') }]
    for raw in images:
        content.append({'type': 'image_url', 'image_url': {'url': prepare_photo(raw), 'detail': 'low'}})
    client = OpenAI(api_key=api_key, timeout=55.0)
    response = client.chat.completions.create(
        model='gpt-4.1-mini',
        response_format={'type': 'json_object'},
        temperature=0.2,
        messages=[{'role': 'system', 'content': SYSTEM_PROMPT},
                  {'role': 'user', 'content': content}],
    )
    parsed = json.loads(response.choices[0].message.content or '{}')
    for k in ('summary', 'visible_strengths', 'visible_concerns', 'landlord_questions', 'not_verifiable_from_photos'):
        if k not in parsed:
            raise ValueError('AI result was incomplete. Please retry.')
    return parsed