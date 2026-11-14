"""Transparent rental comparison with no invented market prices."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class RentInputs:
    monthly_rent: float
    area_sqm: float
    renovation_eur: float = 0.0
    renovation_months: int = 36
    monthly_extra_costs: float = 0.0
    deposit_eur: float = 0.0
    other_upfront_eur: float = 0.0


@dataclass(frozen=True)
class RentResult:
    asking_eur_sqm: float
    effective_monthly_cost: float
    effective_eur_sqm: float
    move_in_cash: float
    comparable_count: int
    median_comp_eur_sqm: float | None
    implied_market_rent: float | None
    deviation_pct: float | None
    verdict: str
    explanation: str
    comparable_rows: list[dict[str, Any]]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None
    import math
    return result if math.isfinite(result) else None


def _fresh_enough(when: Any, max_age_days: int, today: date | None = None) -> bool:
    if when is None or str(when).strip().lower() in ('', 'nan', 'none', 'nat'):
        return True  # Unknown date is disclosed, not silently excluded.
    try:
        observed = date.fromisoformat(str(when)[:10])
    except ValueError:
        return False
    age = ((today or date.today()) - observed).days
    return 0 <= age <= max_age_days


def compare_rent(
    subject: RentInputs,
    comparables: Iterable[dict[str, Any]],
    *,
    max_distance_m: float = 1200,
    max_area_difference: float = 0.40,
    max_age_days: int = 120,
    subject_kind: str = 'Home',
    today: date | None = None,
) -> RentResult:
    """Use only user-provided comparables that satisfy transparent coarse filters.

    Judgment is withheld with fewer than three eligible listings; even then, results
    reflect *asking* rents rather than achieved/contracted prices.
    """
    if subject.monthly_rent <= 0 or subject.area_sqm <= 0:
        raise ValueError('Rent and property size must be positive.')
    if min(subject.renovation_eur, subject.monthly_extra_costs, subject.deposit_eur, subject.other_upfront_eur) < 0:
        raise ValueError('Costs cannot be negative.')
    if subject.renovation_months < 1:
        raise ValueError('Renovation amortization months must be at least one.')

    selected: list[dict[str, Any]] = []
    for entry in comparables:
        rent = _number(entry.get('rent_eur'))
        size = _number(entry.get('area_sqm'))
        distance = _number(entry.get('distance_m'))
        kind = str(entry.get('kind') or 'Home').strip().lower()
        if kind != subject_kind.strip().lower():
            continue
        if rent is None or size is None or rent <= 0 or size <= 0:
            continue
        if distance is None or distance < 0 or distance > max_distance_m:
            continue
        if abs(size / subject.area_sqm - 1) > max_area_difference:
            continue
        if not _fresh_enough(entry.get('observed_on'), max_age_days, today=today):
            continue
        selected.append({
            'address': str(entry.get('address') or 'Unspecified'),
            'rent_eur': rent,
            'area_sqm': size,
            'distance_m': distance,
            'eur_sqm': rent / size,
            'source_url': str(entry.get('source_url') or ''),
            'observed_on': str(entry.get('observed_on') or ''),
        })

    asking = subject.monthly_rent / subject.area_sqm
    effective = subject.monthly_rent + subject.monthly_extra_costs + subject.renovation_eur / subject.renovation_months
    upfront = subject.monthly_rent + subject.deposit_eur + subject.renovation_eur + subject.other_upfront_eur
    if len(selected) < 3:
        return RentResult(
            asking, effective, effective / subject.area_sqm, upfront, len(selected),
            None, None, None, 'Insufficient evidence',
            'At least 3 recent, nearby, similarly-sized comparable rental listings are required.', selected,
        )

    benchmark = median(row['eur_sqm'] for row in selected)
    deviation = 100 * (asking / benchmark - 1)
    if deviation > 12:
        verdict = 'Above comparable asking rents'
    elif deviation < -12:
        verdict = 'Below comparable asking rents'
    else:
        verdict = 'Near comparable asking rents'
    explanation = (
        f'The asking rent is {abs(deviation):.1f}% {"above" if deviation >= 0 else "below"} '
        f'the median €/m² among {len(selected)} eligible user-supplied rental listings. '
        'This is not a valuation, a verified transaction-price comparison, or a condition-adjusted estimate.'
    )
    return RentResult(
        asking, effective, effective / subject.area_sqm, upfront, len(selected),
        benchmark, benchmark * subject.area_sqm, deviation, verdict, explanation, selected,
    )


def result_dict(result: RentResult) -> dict[str, Any]:
    return asdict(result)