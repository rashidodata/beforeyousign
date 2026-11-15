"""Safe, private image bytes for on-device (browser-only) visual analysis.

Requires a previously imported, cached listing and never calls OpenData.
Output is a bounded JPEG with EXIF removed; no arbitrary URL fetching.
"""
from __future__ import annotations

from io import BytesIO
from typing import Callable, Any
from PIL import Image, ImageOps, UnidentifiedImageError
import re


class PhotoUnavailable(Exception):
    """No approved photo is available for this listing."""


def jpeg_for_cached_listing(
    listing_id: str,
    index: int,
    *,
    lookup: Callable[[str], dict[str, Any] | None] | None = None,
    fetch: Callable[[str], bytes] | None = None,
) -> bytes:
    """Read a cached property photo and return a <=768px JPEG, stripped of metadata.

    The listing id and index must both be bounded; photo URL is independently
    validated against an HTTPS Idealista hostname. No billable provider call.
    """
    if not isinstance(listing_id, str) or not re.fullmatch(r'[0-9]{5,14}', listing_id):
        raise ValueError('Invalid listing identifier.')
    if type(index) is not int or not 0 <= index < 8:
        raise ValueError('Photo index must be 0–7.')

    from beforeyousign.import_quota import cached_listing
    from beforeyousign.report_services import fetch_listing_image, _image_url
    listing = (lookup or cached_listing)(listing_id)
    if (not isinstance(listing, dict)
            or listing.get('status') != 'imported'
            or str(listing.get('listing_id')) != listing_id):
        raise PhotoUnavailable('No saved listing available for local image review.')
    urls = listing.get('photo_urls')
    if not isinstance(urls, list) or index >= len(urls):
        raise PhotoUnavailable('Photo is not available from the cached listing.')
    url = _image_url(urls[index])
    if not url:
        raise PhotoUnavailable('Photo host or URL was not authorized.')
    try:
        source = (fetch or fetch_listing_image)(url)
        if not isinstance(source, bytes) or len(source) > 5_000_000:
            raise ValueError('Unexpected photo size.')
        with Image.open(BytesIO(source)) as img:
            if img.width * img.height > 20_000_000:
                raise ValueError('Photo dimensions too large.')
            clean = ImageOps.exif_transpose(img).convert('RGB')
            clean.thumbnail((768, 768))
            buffer = BytesIO()
            clean.save(buffer, format='JPEG', quality=76, optimize=True)
        data = buffer.getvalue()
        if not 1000 <= len(data) <= 2_000_000:
            raise ValueError('Unable to create a bounded preview.')
        return data
    except (ValueError, OSError, UnidentifiedImageError) as exc:
        raise PhotoUnavailable('Advertised image was inaccessible or invalid.') from exc