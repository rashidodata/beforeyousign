"""HTTP adapter for the existing BeforeYouSign Python analysis modules.

Run locally: uvicorn api:app --reload
This API is NOT deployed by GitHub Pages.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from beforeyousign.nearby import LookupError as NearbyLookupError, geocode, nearby_places
from beforeyousign.photo_ai import inspect_photos
from beforeyousign.pricing import RentInputs, compare_rent, result_dict
from madrid_data import inspect_address

app = FastAPI(title="BeforeYouSign API", version="0.1.0", description="Read-only rental due-diligence and analysis endpoints")

ALLOWED_ORIGINS = os.getenv("BYS_CORS_ORIGINS", "https://rashidodata.github.io,http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-BYS-Photo-Token", "X-BYS-Pilot-Code"],
)


class RentRequest(BaseModel):
    monthly_rent: float = Field(gt=0, le=1_000_000)
    area_sqm: float = Field(gt=0, le=100_000)
    renovation_eur: float = Field(default=0, ge=0, le=10_000_000)
    renovation_months: int = Field(default=36, ge=1, le=360)
    monthly_extra_costs: float = Field(default=0, ge=0, le=1_000_000)
    deposit_eur: float = Field(default=0, ge=0, le=10_000_000)
    other_upfront_eur: float = Field(default=0, ge=0, le=10_000_000)
    subject_kind: str = Field(default="Home", pattern="^(Home|Commercial)$")
    max_distance_m: int = Field(default=1200, ge=100, le=5000)
    max_area_difference: float = Field(default=0.4, ge=0.05, le=1)
    comparables: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "beforeyousign-api", "version": "0.1.0"}


@app.post("/api/rent/compare")
def rent_compare(payload: RentRequest) -> dict[str, Any]:
    """Compare only user-supplied rental asking prices, never fabricated market data."""
    subject = RentInputs(
        monthly_rent=payload.monthly_rent,
        area_sqm=payload.area_sqm,
        renovation_eur=payload.renovation_eur,
        renovation_months=payload.renovation_months,
        monthly_extra_costs=payload.monthly_extra_costs,
        deposit_eur=payload.deposit_eur,
        other_upfront_eur=payload.other_upfront_eur,
    )
    try:
        result = compare_rent(
            subject,
            payload.comparables,
            max_distance_m=payload.max_distance_m,
            max_area_difference=payload.max_area_difference,
            subject_kind=payload.subject_kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result_dict(result)


@app.get("/api/nearby")
def nearby(address: str, radius_m: int = 1000) -> dict[str, Any]:
    """Named schools, nurseries, supermarkets, markets, parks and transport via OSM.

    To avoid violating volunteer-hosted Nominatim rate policies, this endpoint is
    disabled until the operator configures a genuine BYS_USER_AGENT with contact.
    Production use additionally requires caching and shared rate limiting.
    """
    if not os.getenv("BYS_USER_AGENT"):
        raise HTTPException(status_code=503, detail="Geocoding requires a configured BYS_USER_AGENT and usage policy.")
    if not 150 <= radius_m <= 2500:
        raise HTTPException(status_code=422, detail="Search radius must be between 150 and 2500 metres.")
    if len(address.strip()) < 7 or len(address) > 250:
        raise HTTPException(status_code=422, detail="Provide a complete street address under 250 characters.")
    try:
        location = geocode(address)
        places = nearby_places(location["lat"], location["lon"], radius=radius_m)
    except (NearbyLookupError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Location provider lookup failed. Check address or try again.") from exc
    return {
        "location": location,
        "places": places,
        "distance_method": "straight-line, not walking time",
        "attribution": "© OpenStreetMap contributors (ODbL)",
    }


@app.get("/api/madrid/records")
def madrid_records(address: str) -> dict[str, Any]:
    """Public Madrid licensing records; missing records never imply compliance."""
    if len(address) > 250:
        raise HTTPException(status_code=422, detail="Address too long.")
    try:
        return inspect_address(address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/photos/analyze")
async def analyze_photos(
    images: list[UploadFile] = File(...),
    context: str = Form(default=""),
    x_bys_photo_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Opt-in server-side photo review; never expose OpenAI credentials in JS.

    Requires an operator-managed token *and* OPENAI_API_KEY. Do not put the
    operator token in the public frontend. Add real user auth and quotas before
    turning this into a public-facing service.
    """
    import secrets

    configured_token = os.getenv("BYS_PHOTO_API_TOKEN", "")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not configured_token or not api_key:
        raise HTTPException(status_code=503, detail="Photo analysis has not been enabled on this server.")
    if not x_bys_photo_token or not secrets.compare_digest(x_bys_photo_token, configured_token):
        raise HTTPException(status_code=401, detail="Photo analysis requires authorization.")
    if not 1 <= len(images) <= 8:
        raise HTTPException(status_code=422, detail="Provide 1–8 photos.")
    raw_images = []
    for image in images:
        if image.content_type not in ("image/jpeg", "image/png"):
            raise HTTPException(status_code=422, detail="Only JPEG or PNG images are allowed.")
        data = await image.read(15_000_001)
        if len(data) > 15_000_000:
            raise HTTPException(status_code=413, detail="Each image must be under 15 MB.")
        raw_images.append(data)
    try:
        return inspect_photos(raw_images, api_key=api_key, context=context[:1000])
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="One of the images could not be analyzed.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The photo analysis service is temporarily unavailable.") from exc


class ListingParseRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000)
    listing_text: str = Field(default="", max_length=40000)


@app.post("/api/listings/parse")
def parse_listing(payload: ListingParseRequest) -> dict[str, Any]:
    """Parse an Idealista link + owner-supplied text; never scrape Idealista."""
    from beforeyousign.listings import analyze_listing_link
    try:
        return analyze_listing_link(payload.url, payload.listing_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ListingImportRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


@app.post("/api/listings/import")
def import_listing_endpoint(
    payload: ListingImportRequest,
    x_bys_import_token: str | None = Header(default=None),
    x_bys_pilot_code: str | None = Header(default=None),
) -> dict[str, Any]:
    """Server-only, permission-gated listing lookup; no direct Idealista scraping.

    The public site can call this endpoint safely while unconfigured. Real
    provider queries remain private until an explicit authorization and usage
    policy have been implemented. Never put an operator token in browser JS.
    """
    import secrets
    from beforeyousign.listings import parse_idealista_url
    from beforeyousign.property_provider import ProviderError, import_listing, provider_configured

    try:
        identity = parse_idealista_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not provider_configured():
        return {
            **identity,
            "status": "provider_unavailable",
            "fields": {},
            "message": "Automatic listing data is not yet authorized. Upload listing screenshots or paste the description instead.",
        }

    # Private pilot: require a shared access code, but allow repeated requests
    # and do not impose the previous three-listing daily cap. Successful results
    # can be served from cache without another paid provider call. A failure
    # is intentionally NOT cached and can be retried immediately.
    if os.getenv("BYS_PUBLIC_IMPORT_ENABLED") == "1":
        pilot_code = os.getenv("BYS_PILOT_ACCESS_CODE", "")
        if not pilot_code or not x_bys_pilot_code or not secrets.compare_digest(pilot_code, x_bys_pilot_code):
            raise HTTPException(status_code=401, detail="A valid private-preview access code is required.")
        from beforeyousign.import_quota import cached_listing, cache_listing
        cached = cached_listing(identity["listing_id"])
        if (cached is not None and cached.get("source_url") == identity["source_url"]
                and cached.get("status") == "imported"
                and "map_pin" in cached and "photo_urls" in cached):
            from beforeyousign.market import enrich_listing_market
            return enrich_listing_market(cached)
        try:
            result = import_listing(payload.url)
            from beforeyousign.market import enrich_listing_market
            result = enrich_listing_market(result)
            if result.get("status") == "imported":
                cache_listing(identity["listing_id"], result)
            return result
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Never let unauthenticated internet requests spend provider credits.
    # A public deployment must first have account auth, quotas, and a
    # durable usage/cost budget; this operator token is only for private QA.
    token = os.getenv("BYS_IMPORT_OPERATOR_TOKEN", "")
    if not token or not x_bys_import_token or not secrets.compare_digest(token, x_bys_import_token):
        return {
            **identity,
            "status": "provider_private",
            "fields": {},
            "message": "Automatic import is currently limited to authorized testing. Add listing screenshots to continue.",
        }
    try:
        from beforeyousign.market import enrich_listing_market
        return enrich_listing_market(import_listing(payload.url))
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/listings/ai-extract")
async def ai_extract_listing(
    url: str = Form(...),
    listing_text: str = Form(default=""),
    screenshots: list[UploadFile] | None = File(default=None),
    x_bys_photo_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """AI data extraction from user-submitted material; operator auth required.

    Public access needs real authentication, rate limiting, and quotas first.
    """
    import secrets
    from beforeyousign.listings import parse_idealista_url
    from beforeyousign.listing_ai import extract_with_ai

    try:
        identity = parse_idealista_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    key, token = os.getenv("OPENAI_API_KEY", ""), os.getenv("BYS_PHOTO_API_TOKEN", "")
    if not key or not token:
        raise HTTPException(status_code=503, detail="AI extraction is not configured.")
    if not x_bys_photo_token or not secrets.compare_digest(x_bys_photo_token, token):
        raise HTTPException(status_code=401, detail="AI extraction requires authorization.")
    if len(listing_text) > 40_000:
        raise HTTPException(status_code=413, detail="Listing text is too long.")
    screenshot_files = screenshots or []
    if len(screenshot_files) > 8:
        raise HTTPException(status_code=422, detail="Maximum eight screenshots.")
    images: list[bytes] = []
    for item in screenshot_files:
        if item.content_type not in ("image/png", "image/jpeg"):
            raise HTTPException(status_code=422, detail="Only PNG and JPEG screenshots are accepted.")
        blob = await item.read(12_000_001)
        if len(blob) > 12_000_000:
            raise HTTPException(status_code=413, detail="Each screenshot must be under 12 MB.")
        images.append(blob)
    if not listing_text.strip() and not images:
        raise HTTPException(status_code=422, detail="Paste listing text or add screenshots.")
    try:
        return {**identity, **extract_with_ai(api_key=key, listing_text=listing_text, screenshots=images)}
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Could not analyze this listing material.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable.") from exc


def _valid_preview_code(supplied: str | None) -> bool:
    import secrets
    stored = os.getenv('BYS_PILOT_ACCESS_CODE', '')
    return (os.getenv('BYS_PUBLIC_IMPORT_ENABLED') == '1' and stored != ''
            and isinstance(supplied, str) and secrets.compare_digest(stored, supplied))


@app.get('/api/neighborhood/summary')
def neighborhood_summary_endpoint(
    lat: float,
    lon: float,
    radius_m: int = 1200,
    x_bys_pilot_code: str | None = Header(default=None),
) -> dict[str, Any]:
    """Named amenities near the provider map pin, from cached OSM data.

    Distances are straight-line estimates from an advertised coordinate;
    the calling frontend must disclose approximate/hidden address status.
    """
    if not _valid_preview_code(x_bys_pilot_code):
        raise HTTPException(status_code=401, detail='A valid preview code is required.')
    from beforeyousign.report_services import neighborhood_summary
    if not 300 <= radius_m <= 2000 or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=422, detail='Invalid area or radius.')
    return neighborhood_summary(lat, lon, radius_m)


@app.post('/api/listings/photo-review')
def listing_photo_review_endpoint(
    payload: ListingImportRequest,
    x_bys_pilot_code: str | None = Header(default=None),
) -> dict[str, Any]:
    """Private, bounded AI review of images already present in cached listings.

    Never calls OpenData again. No preview token or model key is sent to the
    listing image provider. Image fetch hosts are allowlisted; AI spend is
    limited independently from unlimited listing lookups.
    """
    if not _valid_preview_code(x_bys_pilot_code):
        raise HTTPException(status_code=401, detail='A valid preview code is required.')
    from beforeyousign.listings import parse_idealista_url
    from beforeyousign.import_quota import cached_listing
    from beforeyousign.report_services import (
        redis_connection, review_cache_key, fetch_listing_image, _image_url,
    )
    try:
        identity = parse_idealista_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    listing = cached_listing(identity['listing_id'])
    if (not listing or listing.get('source_url') != identity['source_url']
            or listing.get('status') != 'imported'):
        return {'status':'unavailable', 'message':'No previously imported listing was found in cache. Import the listing first; this endpoint never spends OpenData credits.'}
    raw_urls = listing.get('photo_urls') or []
    urls = [url for url in raw_urls[:8] if isinstance(url,str) and _image_url(url)]
    if not urls:
        return {'status':'unavailable','message':'The listing provider did not include usable photo URLs. AI has not analyzed any images.'}
    api_key = os.getenv('OPENAI_API_KEY', '')
    if not api_key:
        return {'status':'unconfigured','message':'AI photo review needs an OPENAI_API_KEY configured privately on Render. The property and neighborhood report still works.'}
    cache=redis_connection()
    if cache is None:
        return {'status':'unavailable','message':'AI review cache is unavailable; no paid model request was made.'}
    key=review_cache_key(identity['listing_id'],urls[:5])
    try:
        saved=cache.get(key)
        if saved:
            import json
            return json.loads(saved)
        if not cache.set(key+':busy','1',nx=True,ex=120):
            return {'status':'loading','message':'Photo analysis is already running for this listing. Try again shortly.'}
    except Exception:
        return {'status':'unavailable','message':'AI review cache is unavailable; no paid model request was made.'}
    try:
        photos=[]
        for url in urls[:5]:
            try:
                data=fetch_listing_image(url)
                if sum(map(len,photos))+len(data) <= 14_000_000:
                    photos.append(data)
            except (ValueError, OSError):
                continue
        if not photos:
            return {'status':'unavailable','message':'The advertised photo host did not provide accessible images; no AI credits were spent.'}
        # This separate budget does not limit regular property checks.
        from datetime import datetime, timezone
        day=datetime.now(timezone.utc).strftime('%Y%m%d')
        budget_key='bys:photo-ai:daily:'+day
        try:
            count=int(cache.incr(budget_key))
            if count==1:
                cache.expire(budget_key,90000)
            max_per_day=min(max(int(os.getenv('BYS_PHOTO_DAILY_LIMIT','30')),1),500)
        except Exception:
            return {'status':'unavailable','message':'AI usage budget is unavailable; no paid model request was made.'}
        if count > max_per_day:
            return {'status':'unavailable','message':'The shared AI photo review budget for today has been reached. Property lookups remain available.'}
        try:
            from beforeyousign.photo_ai import inspect_photos
            context=f'Advertised rental listing {identity["listing_id"]}. Images are third-party advertisements and may be outdated.'
            review=inspect_photos(photos,api_key=api_key,context=context)
        except Exception:
            return {'status':'unavailable','message':'AI photo inspection failed. No visual condition findings were invented.'}
        result={'status':'ok','images_analyzed':len(photos),**review}
        try:
            import json
            cache.setex(key,86400,json.dumps(result))
        except Exception:
            pass
        return result
    finally:
        try:
            cache.delete(key+':busy')
        except Exception:
            pass


# Paid market searches require explicit opt-in and two server-side activation flags.
from beforeyousign.market_routes import router as market_router
app.include_router(market_router)


@app.get('/api/listings/photo-pixels')
def cached_photo_pixels(
    listing_id: str,
    index: int = 0,
    x_bys_pilot_code: str | None = Header(default=None),
) -> Response:
    """Return bounded metadata-free JPEG for on-device WebGPU analysis only.

    This never performs a paid OpenData lookup. A cached import and private
    preview authorization are mandatory; arbitrary image URLs are rejected.
    """
    if not _valid_preview_code(x_bys_pilot_code):
        raise HTTPException(status_code=401, detail='A valid preview code is required.')
    from beforeyousign.photo_proxy import PhotoUnavailable, jpeg_for_cached_listing
    try:
        data = jpeg_for_cached_listing(listing_id, index)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Invalid listing ID or photo index.') from exc
    except PhotoUnavailable as exc:
        raise HTTPException(status_code=404, detail='Cached listing photo is not accessible.') from exc
    return Response(
        content=data,
        media_type='image/jpeg',
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'},
    )


# Automatic property-level photo summaries run only with a separately configured
# private GPU model service and explicit operator enablement.
from beforeyousign.hosted_vision_routes import router as hosted_vision_router
app.include_router(hosted_vision_router)
