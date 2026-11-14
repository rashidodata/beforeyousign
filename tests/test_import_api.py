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