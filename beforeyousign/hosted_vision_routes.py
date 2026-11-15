"""Private pilot: automatic, Redis-cached hosted SmolVLM2 visual reports.

Calling this API never re-fetches OpenData listing details. Jobs are opt-in at
infrastructure level (BYS_VISION_AUTORUN_ENABLED=1) and only execute if a
private GPU model endpoint is configured. BackgroundTasks is suitable for the
single-instance pilot; a durable queue is required before production scale.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from beforeyousign.hosted_vision import (
    VisionError, analyze_listing_images, cache_key, model_host_configured, safe_photo_urls,
)

router = APIRouter()
LOG = logging.getLogger('beforeyousign.hosted_vision_routes')

class VisionRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


def _authorized(pilot_code: str | None) -> bool:
    saved = os.getenv('BYS_PILOT_ACCESS_CODE', '')
    return bool(saved and os.getenv('BYS_PUBLIC_IMPORT_ENABLED') == '1'
                and pilot_code and secrets.compare_digest(pilot_code, saved))


def _listing(url: str) -> dict[str, Any] | None:
    from beforeyousign.listings import parse_idealista_url
    from beforeyousign.import_quota import cached_listing
    try:
        identity = parse_idealista_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    listing = cached_listing(identity['listing_id'])
    if not isinstance(listing, dict) or listing.get('status') != 'imported':
        return None
    if listing.get('source_url') != identity['source_url']:
        return None
    return listing


def _cache():
    from beforeyousign.report_services import redis_connection
    return redis_connection()


def _read(cache: Any, key: str) -> dict[str, Any] | None:
    value = cache.get(key)
    if not value:
        return None
    obj = json.loads(value)
    return obj if isinstance(obj, dict) else None


def _worker(key: str, lock_key: str, listing: dict[str, Any]) -> None:
    """Collect ALL available images, then cache exactly ONE consolidated report."""
    cache = _cache()
    if cache is None:
        return
    try:
        cache.setex(key, 3600, json.dumps({'status': 'processing', 'model':'SmolVLM2-500M'}))
        summary = analyze_listing_images(listing)
        cache.setex(key, 7*86400, json.dumps(summary, ensure_ascii=False))
    except VisionError as exc:
        LOG.warning('Hosted image summary failed: kind=vision')
        cache.setex(key, 300, json.dumps({'status': 'failed', 'message': str(exc)}))
    except Exception as exc:
        LOG.warning('Hosted image summary failed: kind=%s', type(exc).__name__)
        cache.setex(key, 300, json.dumps({
            'status':'failed', 'message':'Hosted image analysis could not finish; no visual details were invented.',
        }))
    finally:
        try:
            cache.delete(lock_key)
        except Exception:
            pass


def _status(listing: dict[str, Any]) -> dict[str, Any]:
    urls = safe_photo_urls(listing)
    if not urls:
        return {'status': 'unavailable', 'message': 'No usable photos were provided with this listing.'}
    if not model_host_configured() or os.getenv('BYS_VISION_AUTORUN_ENABLED') != '1':
        return {'status': 'unconfigured',
                'photos_available': len(urls),
                'message': 'Automatic server-side image review is not activated. A GPU model service must be connected.'}
    cache = _cache()
    if cache is None:
        return {'status': 'unavailable', 'message': 'The visual-report cache is unavailable.'}
    key = cache_key(str(listing['listing_id']), urls)
    try:
        saved = _read(cache, key)
        if saved:
            return saved
    except (ValueError, TypeError):
        return {'status': 'unavailable', 'message': 'Visual-report cache is temporarily unavailable.'}
    return {'status': 'not_started', 'photos_available': len(urls)}


@router.get('/api/listings/visual-summary')
def visual_summary_status(
    url: str,
    x_bys_pilot_code: str | None = Header(default=None),
) -> dict[str, Any]:
    if not _authorized(x_bys_pilot_code):
        raise HTTPException(status_code=401, detail='A valid preview code is required.')
    listing = _listing(url)
    if listing is None:
        return {'status': 'unavailable', 'message': 'Import the listing first. No OpenData lookup was made.'}
    return _status(listing)


@router.post('/api/listings/visual-summary')
def start_visual_summary(
    payload: VisionRequest, tasks: BackgroundTasks,
    x_bys_pilot_code: str | None = Header(default=None),
) -> dict[str, Any]:
    """Called automatically after successful listing import; never bills OpenData."""
    if not _authorized(x_bys_pilot_code):
        raise HTTPException(status_code=401, detail='A valid preview code is required.')
    listing = _listing(payload.url)
    if listing is None:
        return {'status': 'unavailable', 'message': 'Import the listing first. No OpenData lookup was made.'}
    result = _status(listing)
    if result['status'] != 'not_started':
        return result
    urls = safe_photo_urls(listing)
    cache = _cache()
    if cache is None:
        return {'status': 'unavailable', 'message': 'The visual-report cache is unavailable.'}
    key = cache_key(str(listing['listing_id']), urls)
    lock_key = key + ':busy'
    try:
        # Avoid concurrent calls from several clients and repeat GPU charges.
        if not cache.set(lock_key, '1', ex=3600, nx=True):
            return {'status': 'processing', 'photos_available': len(urls)}
        day = datetime.now(timezone.utc).strftime('%Y%m%d')
        budget_key = 'bys:hosted-vision:daily:' + day
        limit = min(max(int(os.getenv('BYS_VISION_DAILY_LIMIT', '20')), 1), 500)
        count = int(cache.incr(budget_key))
        if count == 1:
            cache.expire(budget_key, 90000)
        if count > limit:
            cache.delete(lock_key)
            return {'status': 'daily_limit', 'message': 'The hosted-image daily budget is exhausted.'}
        queued = {'status': 'queued', 'photos_available': len(urls), 'model': 'SmolVLM2-500M'}
        cache.setex(key, 3600, json.dumps(queued))
    except Exception:
        try: cache.delete(lock_key)
        except Exception: pass
        return {'status': 'unavailable', 'message': 'Could not safely reserve hosted image analysis.'}
    tasks.add_task(_worker, key, lock_key, listing)
    return queued