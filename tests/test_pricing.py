from datetime import date
import pytest
from beforeyousign.pricing import RentInputs, compare_rent


def comps():
    return [
        {'address': 'A', 'kind': 'Home', 'rent_eur': 1000, 'area_sqm': 50, 'distance_m': 100, 'observed_on': '2026-11-01'},
        {'address': 'B', 'kind': 'Home', 'rent_eur': 1100, 'area_sqm': 55, 'distance_m': 200, 'observed_on': '2026-11-01'},
        {'address': 'C', 'kind': 'Home', 'rent_eur': 1200, 'area_sqm': 60, 'distance_m': 300, 'observed_on': '2026-11-01'},
    ]


def test_premium_and_costs():
    subject = RentInputs(1300, 50, renovation_eur=1800, renovation_months=36,
                         monthly_extra_costs=50, deposit_eur=2600, other_upfront_eur=300)
    result = compare_rent(subject, comps(), today=date(2026, 11, 14))
    assert result.verdict == 'Above comparable asking rents'
    assert result.median_comp_eur_sqm == 20
    assert result.deviation_pct == pytest.approx(30)
    assert result.effective_monthly_cost == pytest.approx(1400)
    assert result.move_in_cash == pytest.approx(6000)


def test_inadequate_comparables():
    result = compare_rent(RentInputs(900, 50), comps()[:2], today=date(2026, 11, 14))
    assert result.verdict == 'Insufficient evidence'
    assert result.deviation_pct is None


def test_stale_distant_wrong_type_filtered():
    rows = comps() + [
        {'address': 'Old', 'kind': 'Home', 'rent_eur': 30, 'area_sqm': 50, 'distance_m': 20, 'observed_on': '2020-01-01'},
        {'address': 'Far', 'kind': 'Home', 'rent_eur': 30, 'area_sqm': 50, 'distance_m': 9000},
        {'address': 'Shop', 'kind': 'Commercial', 'rent_eur': 30, 'area_sqm': 50, 'distance_m': 100},
        {'address': 'Huge', 'kind': 'Home', 'rent_eur': 30, 'area_sqm': 700, 'distance_m': 100},
    ]
    assert compare_rent(RentInputs(900, 50), rows, today=date(2026, 11, 14)).comparable_count == 3


def test_invalid_prices_rejected():
    with pytest.raises(ValueError):
        compare_rent(RentInputs(0, 50), [])
    with pytest.raises(ValueError):
        compare_rent(RentInputs(800, 40, renovation_eur=-1), [])


def test_commercial_separate():
    rows = [{**r, 'kind': 'Commercial'} for r in comps()]
    assert compare_rent(RentInputs(800, 50), rows, subject_kind='Commercial', today=date(2026, 11, 14)).comparable_count == 3
    assert compare_rent(RentInputs(800, 50), rows, subject_kind='Home', today=date(2026, 11, 14)).comparable_count == 0