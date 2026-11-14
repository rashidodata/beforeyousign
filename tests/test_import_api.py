"""Verify safety of the public one-link endpoint without external queries."""
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)
URL = 'https://www.idealista.com/inmueble/113074128/'


def test_public_endpoint_returns_useful_nonfiction_fallback(monkeypatch):
    monkeypatch.delenv('BYS_LISTING_PROVIDER', raising=False)
    response = client.post('/api/listings/import', json={'url': URL})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'provider_unavailable'
    assert data['listing_id'] == '113074128'
    assert data['fields'] == {}


def test_url_allowlist(monkeypatch):
    monkeypatch.delenv('BYS_LISTING_PROVIDER', raising=False)
    response = client.post('/api/listings/import', json={'url': 'http://127.0.0.1/admin'})
    assert response.status_code == 422


def test_paid_provider_cannot_be_called_anonymously(monkeypatch):
    monkeypatch.setenv('BYS_LISTING_PROVIDER', 'opendata')
    monkeypatch.setenv('BYS_PROVIDER_RIGHTS_CONFIRMED', '1')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY', 'never-charge-this-test')
    monkeypatch.setenv('BYS_IMPORT_OPERATOR_TOKEN', 'local-operator-secret')
    r = client.post('/api/listings/import', json={'url': URL})
    assert r.status_code == 200
    assert r.json()['status'] == 'provider_private'


def test_private_token_allows_authorized_fixture(monkeypatch):
    monkeypatch.setenv('BYS_LISTING_PROVIDER', 'opendata')
    monkeypatch.setenv('BYS_PROVIDER_RIGHTS_CONFIRMED', '1')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY', 'provider-test-key')
    monkeypatch.setenv('BYS_IMPORT_OPERATOR_TOKEN', 'operator-test-key')
    import beforeyousign.property_provider as provider
    record = {'adid': 113074128, 'operation': 'rent', 'price': 1600, 'moreCharacteristics': {'constructedArea': 80}}
    monkeypatch.setattr(provider, '_fetch', lambda *a, **kw: record)
    response = client.post('/api/listings/import', json={'url': URL}, headers={'X-BYS-Import-Token': 'operator-test-key'})
    assert response.status_code == 200
    assert response.json()['fields']['asking_eur_sqm']['value'] == 20
    assert response.json()['independently_verified'] is False


def test_preview_code_enforced_before_provider_or_cache(monkeypatch):
    monkeypatch.setenv('BYS_LISTING_PROVIDER', 'opendata')
    monkeypatch.setenv('BYS_PROVIDER_RIGHTS_CONFIRMED', '0')
    monkeypatch.setenv('BYS_PRIVATE_PILOT_ENABLED', '1')
    monkeypatch.setenv('BYS_PUBLIC_IMPORT_ENABLED', '1')
    monkeypatch.setenv('BYS_PILOT_ACCESS_CODE', 'test-preview-secret')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY', 'test-provider-key')
    response = client.post('/api/listings/import', json={'url': URL})
    assert response.status_code == 401
    response = client.post('/api/listings/import', json={'url': URL}, headers={'X-BYS-Pilot-Code': 'wrong'})
    assert response.status_code == 401


def test_preview_code_allows_cached_record_without_external_request(monkeypatch):
    monkeypatch.setenv('BYS_LISTING_PROVIDER', 'opendata')
    monkeypatch.setenv('BYS_PROVIDER_RIGHTS_CONFIRMED', '0')
    monkeypatch.setenv('BYS_PRIVATE_PILOT_ENABLED', '1')
    monkeypatch.setenv('BYS_PUBLIC_IMPORT_ENABLED', '1')
    monkeypatch.setenv('BYS_PILOT_ACCESS_CODE', 'test-preview-secret')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY', 'test-provider-key')
    import beforeyousign.import_quota as quota
    monkeypatch.setattr(quota, 'cached_listing', lambda listing_id: {
        'status': 'imported', 'source_url': URL, 'listing_id': '113074128',
        'fields': {'monthly_rent_eur': {'value': 1000}}})
    monkeypatch.setattr(quota, 'reserve_lookup', lambda _: (_ for _ in ()).throw(AssertionError('cache should prevent another lookup')))
    response = client.post('/api/listings/import', json={'url': URL}, headers={'X-BYS-Pilot-Code': 'test-preview-secret'})
    assert response.status_code == 200
    assert response.json()['fields']['monthly_rent_eur']['value'] == 1000


def test_preview_quota_fails_closed_without_redis(monkeypatch):
    monkeypatch.setenv('BYS_LISTING_PROVIDER', 'opendata')
    monkeypatch.setenv('BYS_PRIVATE_PILOT_ENABLED', '1')
    monkeypatch.setenv('BYS_PUBLIC_IMPORT_ENABLED', '1')
    monkeypatch.setenv('BYS_PILOT_ACCESS_CODE', 'test-preview-secret')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY', 'test-provider-key')
    monkeypatch.delenv('BYS_REDIS_URL', raising=False)
    import beforeyousign.import_quota as quota
    monkeypatch.setattr(quota, 'cached_listing', lambda listing_id: None)
    response = client.post('/api/listings/import', json={'url': URL}, headers={'X-BYS-Pilot-Code': 'test-preview-secret'})
    assert response.status_code == 200
    assert response.json()['status'] == 'provider_unavailable'