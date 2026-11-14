"""User-triggered, cached-friendly OSM geocoding and nearby amenity lookups.

Intended for exploratory small-scale use only. Respect Nominatim/Overpass policies;
production deployment needs dedicated providers and shared rate limiting.
"""
from __future__ import annotations

import math
import os
from typing import Any
import requests

NOMINATIM_URL = os.getenv('BYS_GEOCODE_URL', 'https://nominatim.openstreetmap.org/search')
OVERPASS_URL = os.getenv('BYS_OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
# Must identify the application; configure real operator contact before public deployment.
USER_AGENT = os.getenv('BYS_USER_AGENT', 'BeforeYouSignRentalPrototype/0.1 (manual-user-search; noncommercial prototype)')


class LookupError(RuntimeError):
    pass


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def _headers() -> dict[str, str]:
    return {'User-Agent': USER_AGENT, 'Accept': 'application/json'}


def geocode(address: str) -> dict[str, Any]:
    if len(address.strip()) < 7:
        raise ValueError('Enter a complete street address and city.')
    try:
        response = requests.get(NOMINATIM_URL, params={
            'q': address.strip(), 'format': 'jsonv2', 'limit': 1, 'addressdetails': 1,
        }, headers=_headers(), timeout=18)
        response.raise_for_status()
        entries = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LookupError(f'Address lookup unavailable: {exc}') from exc
    if not entries:
        raise LookupError('Address not found. Try including the street number, city, and Spain.')
    first = entries[0]
    return {'lat': float(first['lat']), 'lon': float(first['lon']),
            'label': first.get('display_name', address),
            'source_url': f"https://www.openstreetmap.org/{first.get('osm_type', 'node')}/{first.get('osm_id', '')}"}


def overpass_query(lat: float, lon: float, radius: int = 1200) -> str:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinates.')
    if not 150 <= radius <= 2500:
        raise ValueError('Radius must be 150–2500 metres.')
    around = f'(around:{radius},{lat:.6f},{lon:.6f})'
    predicates = [
        '["amenity"="school"]', '["amenity"="kindergarten"]',
        '["shop"~"^(supermarket|grocery|convenience|greengrocer)$"]',
        '["amenity"="marketplace"]', '["railway"="station"]',
        '["station"="subway"]', '["leisure"="park"]',
    ]
    items = ''.join(f'nwr{around}{p};' for p in predicates)
    return '[out:json][timeout:25];(' + items + ');out center tags;'


def classify(tags: dict[str, str]) -> str | None:
    amenity, shop = tags.get('amenity'), tags.get('shop')
    if amenity in ('school', 'kindergarten'):
        return 'Schools & nurseries'
    if amenity == 'marketplace':
        return 'Markets & groceries'
    if shop in ('supermarket', 'grocery', 'convenience', 'greengrocer'):
        return 'Markets & groceries'
    if tags.get('station') == 'subway' or tags.get('railway') == 'station':
        return 'Public transport'
    if tags.get('leisure') == 'park':
        return 'Parks'
    return None


def parse_places(payload: dict[str, Any], origin_lat: float, origin_lon: float,
                 *, max_items: int = 125) -> list[dict[str, Any]]:
    places = []
    seen = set()
    for item in payload.get('elements', []):
        osm_type, osm_id = item.get('type'), item.get('id')
        if (osm_type, osm_id) in seen:
            continue
        seen.add((osm_type, osm_id))
        tags = item.get('tags') or {}
        category = classify(tags)
        if not category:
            continue
        lat = item.get('lat', (item.get('center') or {}).get('lat'))
        lon = item.get('lon', (item.get('center') or {}).get('lon'))
        if lat is None or lon is None:
            continue
        name = tags.get('name') or tags.get('brand') or tags.get('operator')
        if not name:
            # A nearby unnamed element is not an actionable named recommendation.
            continue
        places.append({
            'name': name, 'category': category, 'lat': float(lat), 'lon': float(lon),
            'distance_m': round(distance_m(origin_lat, origin_lon, float(lat), float(lon))),
            'source_url': f'https://www.openstreetmap.org/{osm_type}/{osm_id}',
            'details': tags.get('operator') or '',
        })
    return sorted(places, key=lambda p: p['distance_m'])[:max_items]


def nearby_places(lat: float, lon: float, radius: int = 1200) -> list[dict[str, Any]]:
    try:
        resp = requests.post(OVERPASS_URL, data={'data': overpass_query(lat, lon, radius)},
                             headers=_headers(), timeout=40)
        resp.raise_for_status()
        result = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise LookupError(f'Nearby places unavailable: {exc}') from exc
    return parse_places(result, lat, lon)