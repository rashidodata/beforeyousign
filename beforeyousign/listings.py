"""Evidence-led extraction of rental facts provided by the user.

We intentionally DO NOT scrape Idealista. Its terms require authorization for
programmatic extraction. A URL identifies the property; text or screenshots
supplied by its viewer are the evidence until an authorized API is integrated.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any

IDEALISTA_HOSTS = {"idealista.com", "www.idealista.com", "idealista.pt", "www.idealista.pt", "idealista.it", "www.idealista.it"}
LISTING_ID_RE = re.compile(r"^/inmueble/(\d{5,14})(?:/|$)")


def parse_idealista_url(url: str) -> dict[str, str]:
    """Allowlisted listing identifier extraction. Never dereference arbitrary URLs."""
    if not isinstance(url, str) or len(url) > 2000:
        raise ValueError("Paste a valid Idealista listing link.")
    parsed = urlparse(url.strip())
    if (parsed.scheme != "https" or parsed.hostname not in IDEALISTA_HOSTS
            or parsed.username or parsed.password or parsed.port):
        raise ValueError("Use a full https://www.idealista.com/inmueble/12345678/ link.")
    match = LISTING_ID_RE.match(parsed.path)
    if not match:
        raise ValueError("This doesn't look like an individual Idealista property listing.")
    return {"listing_id": match.group(1), "source_url": f"https://{parsed.hostname}/inmueble/{match.group(1)}/", "website": "idealista"}


def _number(text: str) -> float | None:
    try:
        return float(text.replace(".", "").replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def _field(value: Any = None, evidence: str = "", confidence: str = "unknown", source: str = "not_found") -> dict[str, Any]:
    return {"value": value, "evidence": evidence[:180], "confidence": confidence, "source": source}


def _match_field(patterns: list[str], text: str, *, cast: str = "int", min_value: int = 0, max_value: int = 1_000_000) -> dict[str, Any]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = _number(m.group(1))
            if val is None or not min_value <= val <= max_value:
                continue
            return _field(int(val) if cast == "int" else val, m.group(0), "high", "user_supplied_listing_text")
    return _field()


def _yes_no(text: str, affirmative: list[str], negative: list[str]) -> dict[str, Any]:
    negatives = [re.search(p, text, re.IGNORECASE) for p in negative]
    positives = [re.search(p, text, re.IGNORECASE) for p in affirmative]
    n = next((x for x in negatives if x), None)
    p = next((x for x in positives if x), None)
    if n and (not p or n.start() <= p.start()):
        return _field(False, n.group(0), "medium", "user_supplied_listing_text")
    if p:
        return _field(True, p.group(0), "medium", "user_supplied_listing_text")
    return _field()


def parse_listing_text(text: str) -> dict[str, Any]:
    """Conservative parser of text explicitly copied/pasted by the user.

    No unverifiable bedroom counts, apartment size, precise light rating etc.
    are invented if the user-provided text omits them.
    """
    if not isinstance(text, str) or len(text) > 40_000:
        raise ValueError("Listing text must be 40,000 characters or less.")
    text = " ".join(text.replace("\xa0", " ").split())
    fields: dict[str, Any] = {
        "monthly_rent_eur": _match_field([
            r"(?:€\s*)?(\d[\d., ]{1,11})\s*€\s*/\s*(?:mes|month|m[eê]s)",
            r"(?:alquiler|renta|rent|pre[cç]o)\s*[:\-]?\s*(\d[\d., ]{1,11})\s*€",
            r"€\s*(\d[\d., ]{1,11})\s*(?:/mes|/month)",
        ], text, min_value=100, max_value=100_000),
        "area_sqm": _match_field([
            r"(\d{1,5}(?:[.,]\d{1,2})?)\s*m(?:²|2|\^2|etros cuadrados)(?!\s*/)",
            r"(?:superficie|size|area)\s*[:\-]?\s*(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:m²|m2|sqm)",
        ], text, cast="float", min_value=8, max_value=20_000),
        "bedrooms": _match_field([
            r"(\d{1,2})\s*(?:hab\.?|habitaciones?|dormitorios?|bedrooms?|bed(?:s)?\b|quartos?)",
        ], text, min_value=0, max_value=40),
        "bathrooms": _match_field([
            r"(\d{1,2})\s*(?:baños?|bathrooms?|wc\b|casas de banho)",
        ], text, min_value=0, max_value=40),
        "floor": _match_field([
            r"(?:planta|floor|piso)\s*(\d{1,2})(?:ª|º|a|o)?\b",
            r"(\d{1,2})(?:ª|º)\s*planta",
        ], text, min_value=0, max_value=99),
        "elevator": _yes_no(text, [r"\bcon ascensor\b", r"\bwith (?:an? )?(?:elevator|lift)\b", r"\bcom elevador\b"],
                            [r"\bsin ascensor\b", r"\bwithout (?:an? )?(?:elevator|lift)\b", r"\bsem elevador\b"]),
        "terrace": _yes_no(text, [r"\b(?:con terraza|with terrace|terra[cç]o)\b"], [r"\bsin terraza\b", r"\bwithout terrace\b"]),
        "furnished": _yes_no(text, [r"\b(?:amueblado|amueblada|furnished|mobilado)\b"], [r"\b(?:sin amueblar|unfurnished|no amueblado)\b"]),
        "air_conditioning": _yes_no(text, [r"\b(?:aire acondicionado|air conditioning|ar condicionado)\b"], [r"\b(?:sin aire acondicionado|without air conditioning)\b"]),
    }
    # A rent can be compared only when both rent and floor area are evidenced.
    rent = fields["monthly_rent_eur"]["value"]
    area = fields["area_sqm"]["value"]
    if rent is not None and area is not None:
        fields["asking_eur_sqm"] = _field(round(rent / area, 2), "Computed from supplied rent and area", "high", "calculated")
    else:
        fields["asking_eur_sqm"] = _field()

    # A deliberately wide *scenario* for costs, not a fact about this listing.
    scenario = None
    if rent is not None:
        scenario = {
            "monthly_total_if_extras_100_eur": round(rent + 100, 2),
            "monthly_total_if_extras_250_eur": round(rent + 250, 2),
            "source": "illustrative_scenario_not_property_estimate",
            "explanation": "Illustrative extras of €100–€250/month only; actual utilities and charges need confirmation.",
        }
    missing = [name for name, field in fields.items() if field["source"] == "not_found"]
    positives, concerns = [], []
    if fields["elevator"]["value"] is False:
        concerns.append("No lift is mentioned; verify accessibility, especially on higher floors.")
    if fields["terrace"]["value"] is True:
        positives.append("A terrace is explicitly advertised; confirm its size and exclusivity.")
    if fields["furnished"]["value"] is True:
        positives.append("Advertised as furnished; request an inventory and check condition in person.")
    return {
        "fields": fields,
        "observed_field_count": sum(field["source"] == "user_supplied_listing_text" for field in fields.values()),
        "needs_confirmation": missing,
        "cost_scenario": scenario,
        "visible_pros": positives,
        "potential_cons": concerns,
        "unverified": ["Condition and photo quality", "Exact address", "Building/legal compliance", "Nearby asking rents", "Utilities and fees"],
        "method": "User-provided text only, conservative regular-expression parsing; no automated platform retrieval.",
    }


def analyze_listing_link(url: str, listing_text: str = "") -> dict[str, Any]:
    identity = parse_idealista_url(url)
    data = parse_listing_text(listing_text) if listing_text.strip() else None
    return {
        **identity,
        "status": "analyzed_user_text" if data else "needs_listing_content",
        "verified_auto_import": False,
        "extraction": data,
        "message": (
            "These fields came from text you provided, not an Idealista data feed. Please review them against the listing."
            if data else "Link recognized. Automated Idealista data access requires their authorization. Paste listing text or upload screenshots to extract details now."
        ),
        "official_api_request": "https://developers.idealista.com/access-request",
    }