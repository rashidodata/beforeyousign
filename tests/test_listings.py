import pytest
from fastapi.testclient import TestClient
from api import app
from beforeyousign.listings import analyze_listing_link, parse_idealista_url, parse_listing_text


def test_link_is_canonicalized_and_never_fetched():
    result = analyze_listing_link('https://www.idealista.com/inmueble/113074128/?utm_source=share')
    assert result['source_url'] == 'https://www.idealista.com/inmueble/113074128/'
    assert result['status'] == 'needs_listing_content'
    assert result['extraction'] is None


@pytest.mark.parametrize('url', [
    'http://www.idealista.com/inmueble/113074128/',
    'https://idealista.com.evil.net/inmueble/113074128/',
    'https://www.idealista.com@evil.net/inmueble/113074128/',
    'https://www.idealista.com/buscar/alquiler/',
    'file:///etc/passwd',
])
def test_rejects_untrusted_links(url):
    with pytest.raises(ValueError):
        parse_idealista_url(url)


def test_extracts_spanish_listing_facts():
    text = 'Piso en Calle Luna. 1.500 €/mes 2 hab. 75 m² 3ª planta exterior con ascensor. 1 baño. Amueblado. Con terraza.'
    x = parse_listing_text(text)
    f = x['fields']
    assert f['monthly_rent_eur']['value'] == 1500
    assert f['area_sqm']['value'] == 75
    assert f['bedrooms']['value'] == 2
    assert f['bathrooms']['value'] == 1
    assert f['floor']['value'] == 3
    assert f['elevator']['value'] is True
    assert f['asking_eur_sqm']['value'] == 20
    assert f['terrace']['source'] == 'user_supplied_listing_text'
    assert x['cost_scenario']['source'] == 'illustrative_scenario_not_property_estimate'


def test_unknown_specs_not_invented():
    x = parse_listing_text('Piso atractivo de Madrid. 1.450 €/mes, recién pintado.')
    assert x['fields']['area_sqm']['value'] is None
    assert x['fields']['bedrooms']['value'] is None
    assert x['fields']['asking_eur_sqm']['value'] is None


def test_negative_elevator():
    x = parse_listing_text('Alquiler 1.200 € / mes, 60 m², 4ª planta sin ascensor')
    assert x['fields']['elevator']['value'] is False


def test_api_parse_with_text():
    client = TestClient(app)
    resp = client.post('/api/listings/parse', json={
        'url': 'https://www.idealista.com/inmueble/113074128/',
        'listing_text': '1.600 €/mes 70 m² 2 hab.'})
    assert resp.status_code == 200
    assert resp.json()['extraction']['fields']['asking_eur_sqm']['value'] == 22.86


def test_api_parse_empty_text():
    client = TestClient(app)
    resp = client.post('/api/listings/parse', json={'url': 'https://www.idealista.com/inmueble/113074128/'})
    assert resp.status_code == 200
    assert resp.json()['status'] == 'needs_listing_content'