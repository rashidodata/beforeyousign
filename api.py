"""HTTP adapter for the existing BeforeYouSign Python analysis modules.

Run locally: uvicorn api:app --reload
This API is NOT deployed by GitHub Pages.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
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

    # Private pilot: explicitly authorized participants only. Fail closed if
    # preview code or shared quota storage is missing. Never embed secrets in JS.
    if os.getenv("BYS_PUBLIC_IMPORT_ENABLED") == "1":
        pilot_code = os.getenv("BYS_PILOT_ACCESS_CODE", "")
        if not pilot_code or not x_bys_pilot_code or not secrets.compare_digest(pilot_code, x_bys_pilot_code):
            raise HTTPException(status_code=401, detail="A valid private-preview access code is required.")
        from beforeyousign.import_quota import QuotaUnavailable, reserve_lookup, cached_listing, cache_listing
        cached = cached_listing(identity["listing_id"])
        if cached is not None and cached.get("source_url") == identity["source_url"]:
            return cached
        try:
            quota = reserve_lookup(identity["listing_id"])
        except QuotaUnavailable:
            return {**identity, "status": "provider_unavailable", "fields": {},
                    "message": "Automatic listing service is temporarily unavailable. No lookup was charged."}
        if quota == "limit_reached":
            return {**identity, "status": "daily_limit_reached", "fields": {},
                    "message": "Today's automatic listing import limit has been reached."}
        if quota == "already_requested":
            return {**identity, "status": "already_requested", "fields": {},
                    "message": "This property was requested already today. Please try tomorrow."}
        try:
            result = import_listing(payload.url)
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
        return import_listing(payload.url)
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