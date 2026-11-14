"""Evidence-led neighborhood and listing-photo helpers for the private pilot.

No paid listing lookup takes place here. Coordinates and photographs come from
an already-authorized property-details response. External OSM queries are
bounded and cached; AI photo inspection uses a separately configured API key.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import os
import re
from typing import Any
from urllib.parse import urlsplit

import requests

APP_USER_AGENT = 'BeforeYouSign/0.4 (https://github.com/rashidodata/beforeyousign)'
OVERPASS_ENDPOINTS = (
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)
LOG = logging.getLogger('beforeyousign.report_services')
CATEGORIES = ('Supermarkets', 'Local markets', 'Pharmacies', 'Public transport', 'Parks', 'Schools & nurseries', 'Cafes')
PHOTO_HOST = re.compile(r'^(?:[a-z0-9-]+\.)+idealista\.(?:com|pt|it)$', re.I)


def _number(value: Any, lo: float, hi: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) and lo <= n <= hi else None


def approximate_position(record: dict[str, Any]) -> dict[str, Any] | None:
    """Only provider-supplied coordinates; never manufacture property location."""
    point = record.get('ubication') or {}
    if not isinstance(point, dict):
        return None
    lat = _number(point.get('latitude'), -90, 90)
    lon = _number(point.get('longitude'), -180, 180)
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    hidden = point.get('hasHiddenAddress') is not False
    return {'latitude': lat, 'longitude': lon, 'approximate': hidden,
            'note': 'Distances are measured from an approximate advertised pin, not the exact home.'
            if hidden else 'Distances are straight-line from the provider-listed map pin; walking routes may be longer.'}


def _image_url(raw: Any) -> str | None:
    if not isinstance(raw, str) or len(raw) > 1800:
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme != 'https' or not parsed.hostname or not PHOTO_HOST.fullmatch(parsed.hostname):
            return None
        if parsed.username or parsed.password or parsed.port or parsed.fragment:
            return None
        if not parsed.path.startswith('/'):
            return None
        return raw
    except ValueError:
        return None


def listing_photo_urls(record: dict[str, Any], limit: int = 8) -> list[str]:
    """Extract direct Idealista CDN image URLs only, never advertiser contacts."""
    multimedia = record.get('multimedia') or {}
    if not isinstance(multimedia, dict):
        return []
    images = multimedia.get('images') or []
    if not isinstance(images, list):
        return []
    urls: list[str] = []
    for entry in images:
        url = _image_url(entry.get('url') or entry.get('src')) if isinstance(entry, dict) else _image_url(entry)
        if url and url not in urls:
            urls.append(url)
            if len(urls) >= limit:
                break
    return urls


def geo_distance_m(a: float, b: float, c: float, d: float) -> int:
    r = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c-a), math.radians(d-b)
    z = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(r * 2 * math.asin(min(1, math.sqrt(z))))


def _classify(tags: dict[str, str]) -> str | None:
    shop = tags.get('shop')
    amenity = tags.get('amenity')
    if shop in ('supermarket', 'grocery', 'convenience'):
        return 'Supermarkets'
    if amenity == 'marketplace':
        return 'Local markets'
    if amenity == 'pharmacy' or shop == 'chemist':
        return 'Pharmacies'
    if tags.get('railway') in ('station', 'tram_stop', 'subway_entrance') or tags.get('station') == 'subway' or tags.get('highway') == 'bus_stop':
        return 'Public transport'
    if tags.get('leisure') == 'park':
        return 'Parks'
    if amenity in ('school', 'kindergarten'):
        return 'Schools & nurseries'
    if amenity == 'cafe':
        return 'Cafes'
    return None


def parse_nearby(payload: dict[str, Any], lat: float, lon: float, *, max_each: int = 3) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORIES}
    dedupe: set[tuple[str,str]] = set()
    if not isinstance(payload, dict):
        return groups
    for item in payload.get('elements', [])[:3000]:
        if not isinstance(item, dict):
            continue
        tags = item.get('tags') or {}
        if not isinstance(tags, dict):
            continue
        cat = _classify(tags)
        name = tags.get('name') or tags.get('brand') or tags.get('operator')
        if not cat or not isinstance(name, str) or not name.strip():
            continue
        vlat = item.get('lat', (item.get('center') or {}).get('lat'))
        vlon = item.get('lon', (item.get('center') or {}).get('lon'))
        plat, plon = _number(vlat,-90,90), _number(vlon,-180,180)
        if plat is None or plon is None:
            continue
        typ, identifier = item.get('type'), item.get('id')
        if typ not in ('node','way','relation') or not isinstance(identifier, int):
            continue
        normalized = (cat, name.casefold().strip())
        if normalized in dedupe:
            continue
        dedupe.add(normalized)
        groups[cat].append({'name': name.strip()[:90], 'distance_m': geo_distance_m(lat,lon,plat,plon),
                            'source_url': f'https://www.openstreetmap.org/{typ}/{identifier}'})
    return {cat: sorted(places, key=lambda x:x['distance_m'])[:max_each] for cat,places in groups.items()}


def overpass_query(lat: float, lon: float, radius_m: int = 1200) -> str:
    if not (-90<=lat<=90 and -180<=lon<=180 and 300<=radius_m<=2000):
        raise ValueError('Invalid neighborhood location or radius.')
    around = f'(around:{radius_m},{lat:.6f},{lon:.6f})'
    tags = [
        '["shop"~"^(supermarket|grocery|convenience|chemist)$"]',
        '["amenity"~"^(marketplace|pharmacy|school|kindergarten|cafe)$"]',
        '["railway"~"^(station|tram_stop|subway_entrance)$"]',
        '["station"="subway"]',
        '["highway"="bus_stop"]',
        '["leisure"="park"]',
    ]
    return '[out:json][timeout:20];(' + ''.join(f'nwr{around}{tag};' for tag in tags) + ');out center tags;'


def redis_connection():
    url = os.getenv('BYS_REDIS_URL', '')
    if not url.startswith(('redis://','rediss://')):
        return None
    try:
        import redis
        return redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=2)
    except Exception:
        return None


def neighborhood_summary(lat: float, lon: float, radius_m: int = 1200) -> dict[str, Any]:
    """Cached amenity summary via two known public Overpass instances.

    A failed public query is cached for four minutes. Never repeat against
    the same host immediately; only use a second host for transport and 5xx
    failures, not rate limits, invalid queries, or Overpass runtime remarks.
    """
    if _number(lat,-90,90) is None or _number(lon,-180,180) is None or not 300<=radius_m<=2000:
        return {'status':'unavailable','reason':'Location must be a valid map coordinate.'}
    cache = redis_connection()
    if cache is None:
        return {'status':'unavailable','reason':'Nearby-place cache is not configured yet.'}
    key = f'bys:neighborhood:v3:{lat:.4f}:{lon:.4f}:{radius_m}'
    try:
        raw = cache.get(key)
        if raw:
            return json.loads(raw)
        lock_key = key + ':busy'
        if not cache.set(lock_key, '1', ex=90, nx=True):
            return {'status':'loading','reason':'Nearby places are being looked up. Try again in a minute.'}
    except Exception:
        return {'status':'unavailable','reason':'Nearby-place cache is temporarily unavailable.'}
    result = {'status':'unavailable','reason':'OpenStreetMap lookup is temporarily unavailable. Retry after a few minutes; no nearby distances were invented.'}
    query = overpass_query(lat, lon, radius_m)
    try:
        for index, endpoint in enumerate(OVERPASS_ENDPOINTS):
            source = 'primary' if index == 0 else 'secondary'
            try:
                response = requests.post(
                    endpoint, data={'data':query}, timeout=(5, 26),
                    headers={'User-Agent':APP_USER_AGENT,'Accept':'application/json'},
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                LOG.warning('Neighborhood Overpass request failed: source=%s kind=transport exception=%s',
                            source, type(exc).__name__)
                continue
            code = response.status_code
            if code != 200:
                LOG.warning('Neighborhood Overpass request failed: source=%s kind=http status=%s', source, code)
                # Respect the public service: do not bypass its rate limit.
                if code not in (500, 502, 503, 504):
                    break
                continue
            if len(response.content) > 4_000_000:
                LOG.warning('Neighborhood Overpass response oversized: source=%s', source)
                break
            try:
                payload = response.json()
            except ValueError:
                LOG.warning('Neighborhood Overpass returned invalid JSON: source=%s', source)
                break
            if not isinstance(payload, dict) or 'remark' in payload:
                LOG.warning('Neighborhood Overpass returned incomplete data: source=%s kind=remark_or_format', source)
                break
            if not isinstance(payload.get('elements'), list):
                LOG.warning('Neighborhood Overpass response missing elements: source=%s', source)
                break
            groups = parse_nearby(payload,lat,lon)
            if not any(groups.values()):
                LOG.warning('Neighborhood Overpass returned no named amenities: source=%s', source)
                break
            result = {'status':'ok','groups':groups,'distance_method':'straight_line',
                      'attribution':'OpenStreetMap contributors (ODbL)',
                      'message':'Named, mapped amenities only. Walking routes and opening hours are not verified.'}
            break
    finally:
        try:
            cache.setex(key, 21600 if result['status']=='ok' else 240, json.dumps(result))
            cache.delete(lock_key)
        except Exception:
            LOG.warning('Neighborhood cache write failed: kind=cache')
    return result


def fetch_listing_image(url: str, *, max_bytes: int = 5_000_000) -> bytes:
    """Fetch only HTTPS image URLs from Idealista subdomains. No redirects."""
    if not _image_url(url):
        raise ValueError('Untrusted image source.')
    try:
        with requests.get(url, timeout=(4,12), stream=True, allow_redirects=False,
                          headers={'User-Agent':APP_USER_AGENT,'Accept':'image/jpeg,image/webp,image/png'}) as response:
            if response.status_code != 200:
                raise ValueError('Image source unavailable.')
            if not response.headers.get('Content-Type','').lower().startswith('image/'):
                raise ValueError('Image source did not return a picture.')
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError('Listing image is too large.')
                chunks.append(chunk)
            if size < 3000:
                raise ValueError('Listing image is empty or too small.')
            return b''.join(chunks)
    except requests.RequestException as exc:
        raise ValueError('Listing image source is temporarily unavailable.') from exc


def review_cache_key(listing_id: str, urls: list[str]) -> str:
    digest=hashlib.sha256(('|'.join(urls)).encode('utf-8')).hexdigest()[:18]
    return f'bys:photo-review:v2:{listing_id}:{digest}'