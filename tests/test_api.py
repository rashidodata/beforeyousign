"""API smoke tests without external network access or paid AI calls."""
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'


def test_rent_no_comparables():
    r = client.post('/api/rent/compare', json={'monthly_rent': 1500, 'area_sqm': 75})
    assert r.status_code == 200
    assert r.json()['asking_eur_sqm'] == 20
    assert r.json()['verdict'] == 'Insufficient evidence'


def test_rent_rejects_zero_area():
    r = client.post('/api/rent/compare', json={'monthly_rent': 1500, 'area_sqm': 0})
    assert r.status_code == 422


def test_nearby_requires_operator_config(monkeypatch):
    monkeypatch.delenv('BYS_USER_AGENT', raising=False)
    r = client.get('/api/nearby', params={'address': 'Calle Caceres 41, Madrid'})
    assert r.status_code == 503


def test_photo_disabled_without_secrets(monkeypatch):
    monkeypatch.delenv('BYS_PHOTO_API_TOKEN', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    r = client.post('/api/photos/analyze', files={'images': ('test.jpg', b'123', 'image/jpeg')})
    assert r.status_code == 503