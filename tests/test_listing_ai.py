from fastapi.testclient import TestClient
from api import app
from beforeyousign.listing_ai import _validate_result


def test_ai_result_never_invents_critical_values():
    raw = {"fields": {"monthly_rent_eur": {"value": 1500, "status": "inferred", "confidence": "low", "evidence": "looks costly"},
                      "terrace": {"value": True, "status": "observed", "confidence": "high", "evidence": "con terraza"}}}
    result = _validate_result(raw)
    assert result["fields"]["monthly_rent_eur"]["value"] is None
    assert result["fields"]["terrace"]["value"] is True
    assert result["fields"]["area_sqm"]["status"] == "unknown"


def test_no_ai_without_server_config(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('BYS_PHOTO_API_TOKEN', raising=False)
    r = TestClient(app).post('/api/listings/ai-extract', data={
        'url': 'https://www.idealista.com/inmueble/113074128/',
        'listing_text': '1.500 €/mes'})
    assert r.status_code == 503