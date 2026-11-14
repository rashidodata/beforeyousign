"""Exportable evidence-aware Markdown property report."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .pricing import RentInputs, RentResult


def build_report(property_info: dict[str, Any], costs: RentInputs, rent: RentResult,
                 places: list[dict[str, Any]], photos: dict[str, Any] | None = None) -> str:
    address = property_info.get('address') or 'Unspecified location'
    lines = [f'# BeforeYouSign — rental review', '', f'**Property:** {address}',
             f'**Prepared:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
             f'**Listing:** {property_info.get("listing_url") or "Not supplied"}', '',
             '## Price and up-front costs', '',
             f'- Asking rent: €{costs.monthly_rent:,.0f}/month',
             f'- Area: {costs.area_sqm:g} m²',
             f'- Asking price: €{rent.asking_eur_sqm:,.2f}/m²/month',
             f'- Monthly effective occupancy cost (incl. amortized renovation and extras): €{rent.effective_monthly_cost:,.2f}',
             f'- Effective occupancy cost: €{rent.effective_eur_sqm:,.2f}/m²/month',
             f'- Cash needed to move in (assuming first rent + supplied costs/deposit): €{rent.move_in_cash:,.2f}',
             f'- Renovation assumption: €{costs.renovation_eur:,.0f} over {costs.renovation_months} months', '',
             '## Rental asking-price comparison', '',
             f'**Finding:** {rent.verdict}', '', rent.explanation, '',
             f'**Eligible listings:** {rent.comparable_count}', '']
    if rent.median_comp_eur_sqm is not None:
        lines += [f'- Median comparable asking rent: €{rent.median_comp_eur_sqm:,.2f}/m²/month',
                  f'- Comparable-implied subject rent: €{rent.implied_market_rent:,.0f}/month',
                  f'- Asking-price premium/discount: {rent.deviation_pct:+.1f}%', '']
    for row in rent.comparable_rows:
        lines.append(f'- {row["address"]}: €{row["rent_eur"]:,.0f}/month, {row["area_sqm"]:g} m², '
                     f'{row["distance_m"]:,.0f}m away, source: {row["source_url"] or "not supplied"}')
    lines += ['', '## Nearby services (straight-line distances, not walking times)', '']
    if places:
        for item in places[:25]:
            lines.append(f'- {item["category"]}: {item["name"]} — {item["distance_m"]}m '
                         f'({item["source_url"]})')
    else:
        lines.append('No location lookup results available. This does not mean no services exist.')
    lines += ['', '## Visual review of listing photos', '']
    if photos:
        lines.append(photos.get('summary', ''))
        for key, heading in [('visible_strengths', 'Visible strengths'), ('visible_concerns', 'Visible concerns')]:
            lines += ['', f'### {heading}']
            for finding in photos.get(key, []):
                if isinstance(finding, dict):
                    lines.append(f'- {finding.get("finding", "")} ({finding.get("evidence_photo", "")})')
        lines += ['', '### Questions for the landlord']
        lines += [f'- {q}' for q in photos.get('landlord_questions', [])]
        lines += ['', '### Not verifiable from photos']
        lines += [f'- {q}' for q in photos.get('not_verifiable_from_photos', [])]
    else:
        lines.append('No AI visual review performed.')
    lines += ['', '## Limitations', '',
              '- Rental comparables are supplied by the user, not automatically sourced or verified. Asking prices are not signed lease prices.',
              '- The comparison does not adjust for all differences in finish, floor, furnishing, outdoor space, or lease terms.',
              '- Nearby features come from volunteer-contributed OpenStreetMap data and may be incomplete or outdated.',
              '- Distances are straight-line approximations; they are not pedestrian routes or travel times.',
              '- Photo analysis is an AI observation of supplied pictures, not a building inspection or legal opinion.',
              '- Verify licensing, habitability, charges, and contract terms with a qualified professional where needed.',
              '', 'Map and amenity data: © OpenStreetMap contributors (ODbL).', '']
    return '\n'.join(lines)