"""Optional, permission-gated property lookup using a documented data-provider API.

This module DOES NOT connect to Idealista or scrape any listing. The configured
provider is an independent third party. Enable only when contract/license rights
and the provider's charge model have been independently checked.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import json
import logging
import re
import math
import os
from threading import Lock
import time
from typing import Any, Callable

import requests

from beforeyousign.listings import parse_idealista_url

PROVIDER_ENDPOINT = "https://api.opendata-api.com/api/project/idealista/property-details"
LOG = logging.getLogger("beforeyousign.property_provider")
CACHE_TTL_SECONDS = 3600
CACHE_MAX_ENTRIES = 128
MAX_RESPONSE_BYTES = 2_000_000
_CACHE: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_LOCK = Lock()


class ProviderError(Exception):
    """Safe public exception: never include provider keys or the complete request URL."""


def _safe_error_details(response: Any, api_key: str) -> tuple[str, str]:
    """Inspect a bounded upstream error body. Log metadata only, no secrets/PII."""
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=2048):
            if total >= 8192:
                break
            chunks.append(chunk[:8192-total])
            total += len(chunks[-1])
    except (requests.RequestException, OSError):
        return "unreadable", ""
    body = b"".join(chunks)
    if not body:
        return "empty", ""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return "non_json", ""
    if not isinstance(data, dict):
        return "non_object_json", ""
    candidate = data.get('error_code') or data.get('code') or data.get('error')
    if isinstance(candidate, dict):
        candidate = candidate.get('code') or candidate.get('type')
    if isinstance(candidate, (int, float)):
        candidate = str(candidate)
    if not isinstance(candidate, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', candidate):
        candidate = ""
    # We intentionally do not log the provider's free-text message: it may
    # contain the request URL, API key, advertiser data, or other PII.
    return "json", candidate


def _http_error(response: Any, api_key: str) -> ProviderError:
    status = int(response.status_code)
    body_type, code = _safe_error_details(response, api_key)
    LOG.warning("OpenData request failed: upstream_status=%s body_type=%s error_code=%s",
                status, body_type, code or 'none')
    hint = {
        400: "The API rejected the request parameters.",
        401: "The OpenData API key was rejected.",
        402: "The provider requires additional credits or subscription access.",
        403: "The provider denied access to this operation.",
        404: "The listing was not available from the provider.",
        429: "The provider's request limit has been reached.",
        500: "The provider reported an internal error.",
        502: "The provider's upstream lookup failed; its own service may be temporarily unavailable.",
        503: "The provider is temporarily unavailable.",
        504: "The provider timed out while retrieving the listing.",
    }.get(status, "The provider did not return a successful response.")
    suffix = (' (provider code: ' + code + ')' if code else '')
    return ProviderError(f"OpenData API returned HTTP {status}. {hint}{suffix} No automatic retries were made.")


def _num(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, str):
        value = value.replace("\u00a0", "").replace(" ", "").replace("€", "")
        if "," in value and "." in value:
            value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
        elif "," in value:
            value = value.replace(",", ".")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def _text(value: Any, length: int = 150) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:length]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _field(value: Any, path: str, *, confidence: str = "medium") -> dict[str, Any]:
    if value is None:
        return {"value": None, "status": "unknown", "source": "not_found", "evidence": "", "confidence": "unknown"}
    return {
        "value": value,
        "status": "observed",
        "source": "third_party_listing_feed",
        "evidence": "Advertised value supplied by listing-data provider (" + path + ")",
        "confidence": confidence,
    }


def provider_configured(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (
        env.get("BYS_LISTING_PROVIDER") == "opendata"
        and bool(env.get("BYS_OPENDATA_API_KEY", "").strip())
        and (
            env.get("BYS_PROVIDER_RIGHTS_CONFIRMED") == "1"
            or (
                env.get("BYS_PRIVATE_PILOT_ENABLED") == "1"
                and env.get("BYS_PUBLIC_IMPORT_ENABLED") == "1"
                and bool(env.get("BYS_PILOT_ACCESS_CODE", ""))
            )
        )
    )


def _fetch(id_number: str, country: str, *, api_key: str, get: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Fetch JSON from a fixed HTTPS provider host, bounded to 2 MB; no SSRF URL input.

    This method is never invoked without explicit configuration and a provider key.
    """
    requester = get or requests.get
    try:
        response = requester(
            PROVIDER_ENDPOINT,
            params={"key": api_key, "language": "es", "location": country, "propertyId": id_number},
            timeout=(3, 12),
            stream=True,
            allow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "BeforeYouSign/0.2"},
        )
        with response:
            if response.status_code != 200:
                raise _http_error(response, api_key)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=32768):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ProviderError("Listing provider returned an oversized record.")
                chunks.append(chunk)
        result = json.loads(b"".join(chunks))
        if not isinstance(result, dict):
            raise ProviderError("Listing provider returned an unexpected data format.")
        return result
    except ProviderError:
        raise
    except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
        raise ProviderError("Listing provider is temporarily unavailable.") from exc


def normalize_property(payload: dict[str, Any], listing_url: str, *, retrieved_at: str | None = None) -> dict[str, Any]:
    """Map one provider listing into narrow public fields; omit advertiser PII and photos.

    Treat all fields as *advertised* values, not independently verified facts.
    Refuse sales and mismatched listing IDs rather than mislabeling purchase price
    as monthly rent. Latitude/longitude are not exposed when address is hidden.
    """
    identity = parse_idealista_url(listing_url)
    listing_id = identity["listing_id"]
    data_id = str(payload.get("adid") or payload.get("propertyId") or "")
    if data_id != listing_id:
        raise ProviderError("The provider returned a different listing ID.")
    operation = str(payload.get("operation") or "").strip().lower()
    if operation not in {"rent", "rental", "alquiler"}:
        return {**identity, "status": "not_confirmed_rental", "listing_operation": operation or "unknown",
                "message": "This listing was not confirmed as a rental property, so no monthly rent is reported.",
                "fields": {}, "source": "third_party_listing_feed", "independently_verified": False}

    char = _dict(payload.get("moreCharacteristics"))
    location = _dict(payload.get("ubication"))
    energy = _dict(payload.get("energyCertification"))
    price_info = _dict(payload.get("priceInfo"))
    raw_price = price_info.get("amount", payload.get("price"))
    if isinstance(raw_price, dict):
        raw_price = raw_price.get("amount")
    rent = _num(raw_price, 100, 100000)
    area = _num(char.get("constructedArea"), 8, 20000)
    bedroom = _num(char.get("roomNumber"), 0, 40)
    bath = _num(char.get("bathNumber"), 0, 40)
    floor_raw = char.get("floor")
    floor = int(v) if (v := _num(floor_raw, 0, 120)) is not None else _text(floor_raw, 35)
    elevator = char.get("lift")
    if not isinstance(elevator, bool):
        elevator = None
    furnished = char.get("furnished")
    if not isinstance(furnished, bool):
        furnished = None
    terrace = char.get("terrace")
    if not isinstance(terrace, bool):
        terrace = None
    air_cond = char.get("airConditioning")
    if not isinstance(air_cond, bool):
        air_cond = None
    cert = _text(energy.get("energyRating") or char.get("energyPerformance"), 25)
    neighbourhood = _text(location.get("locationName") or location.get("title"), 120)
    kind = _text(payload.get("propertyType"), 50)

    fields = {
        "monthly_rent_eur": _field(rent, "priceInfo.amount/price"),
        "area_sqm": _field(area, "moreCharacteristics.constructedArea"),
        "bedrooms": _field(int(bedroom) if bedroom is not None else None, "moreCharacteristics.roomNumber"),
        "bathrooms": _field(int(bath) if bath is not None else None, "moreCharacteristics.bathNumber"),
        "floor": _field(floor, "moreCharacteristics.floor"),
        "elevator": _field(elevator, "moreCharacteristics.lift"),
        "terrace": _field(terrace, "moreCharacteristics.terrace"),
        "furnished": _field(furnished, "moreCharacteristics.furnished"),
        "air_conditioning": _field(air_cond, "moreCharacteristics.airConditioning"),
        "energy_certificate": _field(cert, "energyCertification/energyPerformance", confidence="low"),
        "property_type": _field(kind, "propertyType"),
        "city_or_area": _field(neighbourhood, "ubication.locationName/title"),
    }
    asking = round(rent / area, 2) if rent is not None and area else None
    fields["asking_eur_sqm"] = _field(asking, "calculated from advertised price and constructed area", confidence="high")
    if asking is not None:
        fields["asking_eur_sqm"]["source"] = "calculated"
    visible_pros: list[str] = []
    concerns: list[str] = []
    if elevator is True:
        visible_pros.append("The listing advertises an elevator; verify that it serves the apartment's floor.")
    elif elevator is False:
        concerns.append("The listing says there is no elevator; check accessibility.")
    if terrace is True:
        visible_pros.append("A terrace is advertised; verify usable area and exclusive access.")
    if furnished is True:
        visible_pros.append("Advertised as furnished; check the inventory and condition.")
    elif furnished is False:
        concerns.append("Advertised as unfurnished; budget separately for furnishings.")
    if not neighbourhood:
        concerns.append("The precise location is not evidenced by the provider record.")
    hidden_address = location.get("hasHiddenAddress") is not False
    return {
        **identity,
        "status": "imported",
        "provider": "opendata",
        "source": "third_party_listing_feed",
        "independently_verified": False,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "listing_operation": operation,
        "listing_state": _text(payload.get("state"), 35) or "unknown",
        "location_precision": "approximate_or_hidden" if hidden_address else "provider_advertised",
        "fields": fields,
        "pros": visible_pros,
        "cons": concerns,
        "needs_confirmation": [k for k, f in fields.items() if f["status"] == "unknown"],
        "valuation": {
            "verdict": "Insufficient evidence",
            "message": "A fair-price judgment requires recent nearby rental comparables; no market median has been assumed.",
            "asking_eur_sqm": asking,
            "median_comparable_eur_sqm": None,
        },
        "message": "Property details imported from an independent data provider, not verified with the landlord or Idealista.",
    }


def import_listing(url: str, *, env: dict[str, str] | None = None,
                   get: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One lookup per cache miss; returns safe status if provider access is absent."""
    identity = parse_idealista_url(url)
    env = os.environ if env is None else env
    if not provider_configured(env):
        return {**identity, "status": "provider_unavailable", "fields": {},
                "message": "Automatic listing import is not enabled. Provide screenshots or listing text to continue.",
                "provider_requested": False}
    key = (identity["listing_id"], identity["source_url"].split('/')[2])
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is not None and time.monotonic() - entry[0] < CACHE_TTL_SECONDS:
            _CACHE.move_to_end(key)
            return entry[1]
    country = "pt" if "idealista.pt" in key[1] else "it" if "idealista.it" in key[1] else "es"
    payload = _fetch(identity["listing_id"], country, api_key=env["BYS_OPENDATA_API_KEY"], get=get)
    result = normalize_property(payload, identity["source_url"])
    with _LOCK:
        _CACHE[key] = (time.monotonic(), result)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_MAX_ENTRIES:
            _CACHE.popitem(last=False)
    return result