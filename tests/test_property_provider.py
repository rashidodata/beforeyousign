"""No network, credentials, or real property data used by these tests."""
from __future__ import annotations

import json

import pytest

from beforeyousign.property_provider import (
    ProviderError, _fetch, import_listing, normalize_property, provider_configured,
)

URL = 'https://www.idealista.com/inmueble/113074128/'
RECORD = {
    'adid': 113074128,
    'operation': 'rent',
    'priceInfo': {'amount': 1500},
    'moreCharacteristics': {'roomNumber': 2, 'bathNumber': 1, 'constructedArea': 75, 'floor': 3, 'lift': True},
    'ubication': {'locationName': 'Madrid', 'hasHiddenAddress': True},
    'propertyType': 'flat',
    'state': 'active',
}


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv('BYS_LISTING_PROVIDER', raising=False)
    answer = import_listing(URL)
    assert answer['status'] == 'provider_unavailable'
    assert answer['fields'] == {}


def test_requires_contract_and_key():
    assert not provider_configured({'BYS_LISTING_PROVIDER':'opendata','BYS_OPENDATA_API_KEY':'key'})
    assert not provider_configured({'BYS_LISTING_PROVIDER':'opendata','BYS_PROVIDER_RIGHTS_CONFIRMED':'1'})
    assert provider_configured({'BYS_LISTING_PROVIDER':'opendata','BYS_PROVIDER_RIGHTS_CONFIRMED':'1','BYS_OPENDATA_API_KEY':'key'})


def test_normalized_known_fields_with_evidence():
    answer=normalize_property(RECORD,URL,retrieved_at='2026-11-14T00:00:00Z')
    assert answer['status']=='imported'
    assert answer['fields']['asking_eur_sqm']['value']==20
    assert answer['fields']['bedrooms']['value']==2
    assert answer['fields']['monthly_rent_eur']['source']=='third_party_listing_feed'
    assert answer['fields']['furnished']['status']=='unknown'
    assert answer['location_precision']=='approximate_or_hidden'
    assert answer['valuation']['verdict']=='Insufficient evidence'
    assert 'contactInfo' not in answer


def test_cannot_confuse_sale_price_with_rent():
    result=normalize_property({**RECORD,'operation':'sale'},URL)
    assert result['status']=='not_confirmed_rental'
    assert result['fields']=={}


def test_does_not_confuse_listing_ids():
    with pytest.raises(ProviderError):
        normalize_property({**RECORD, 'adid': 999999999},URL)


def test_price_must_be_plausible():
    result=normalize_property({**RECORD,'priceInfo':{'amount':0}},URL)
    assert result['fields']['monthly_rent_eur']['status']=='unknown'
    assert result['fields']['asking_eur_sqm']['value'] is None


def test_invalid_url_not_used_for_network():
    with pytest.raises(ValueError):
        import_listing('https://example.com/secret?key=abc',env={'BYS_LISTING_PROVIDER':'opendata','BYS_PROVIDER_RIGHTS_CONFIRMED':'1','BYS_OPENDATA_API_KEY':'x'})


class FakeResponse:
    status_code=200
    def __init__(self, obj): self.obj=obj
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def iter_content(self, chunk_size=32768):
        yield json.dumps(self.obj).encode()


def test_only_fixed_endpoint_called_and_no_url_to_provider():
    calls=[]
    def fake_get(url, **kwargs):
        calls.append((url,kwargs))
        return FakeResponse(RECORD)
    result=_fetch('113074128','es',api_key='secret-value',get=fake_get)
    assert result['adid']==113074128
    assert calls[0][0]=='https://api.opendata-api.com/api/project/idealista/property-details'
    assert calls[0][1]['params']['propertyId']=='113074128'
    assert calls[0][1]['allow_redirects'] is False


def test_no_provider_exceptions_leak_key():
    def bad(*args,**kwargs):
        from requests import RequestException
        raise RequestException('secret')
    with pytest.raises(ProviderError) as exc:
        _fetch('113074128','es',api_key='secret',get=bad)
    assert 'secret' not in str(exc.value)


def test_oversized_response_rejected():
    class Big(FakeResponse):
        def iter_content(self, chunk_size=32768):
            yield b'x' * 2_000_001
    with pytest.raises(ProviderError,match='oversized'):
        _fetch('113074128','es',api_key='x',get=lambda *a,**k:Big(RECORD))


def test_private_pilot_can_use_existing_provider_key_without_commercial_flag():
    env = {'BYS_LISTING_PROVIDER':'opendata', 'BYS_OPENDATA_API_KEY':'test-key',
           'BYS_PRIVATE_PILOT_ENABLED':'1', 'BYS_PUBLIC_IMPORT_ENABLED':'1', 'BYS_PILOT_ACCESS_CODE':'private-code'}
    assert provider_configured(env)
    env.pop('BYS_PILOT_ACCESS_CODE')
    assert not provider_configured(env)


def test_idealista_112592538_request_matches_documented_api_without_spending_credits():
    calls = []
    class Upstream502(FakeResponse):
        status_code = 502
        def iter_content(self, chunk_size=32768):
            yield b'{"error_code":"upstream_unavailable","message":"Temporary backend issue"}'
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Upstream502({})
    with pytest.raises(ProviderError, match=r'HTTP 502.*upstream lookup failed.*upstream_unavailable'):
        _fetch('112592538', 'es', api_key='test-key', get=fake_get)
    url, params = calls[0]
    assert url == 'https://api.opendata-api.com/api/project/idealista/property-details'
    assert params['params'] == {'key':'test-key','language':'es','location':'es','propertyId':'112592538'}
    assert params['allow_redirects'] is False


def test_upstream_error_message_never_exposes_provider_key(caplog):
    class ErrorResponse(FakeResponse):
        status_code = 502
        def iter_content(self, chunk_size=32768):
            yield b'{"message":"key=secret-key and user@example.com", "error_code":"upstream_error"}'
    with pytest.raises(ProviderError) as exc:
        _fetch('112592538','es',api_key='secret-key',get=lambda *a, **kw:ErrorResponse({}))
    assert 'secret-key' not in str(exc.value)
    assert 'secret-key' not in caplog.text
    assert 'user@example.com' not in caplog.text


def test_html_gateway_error_yields_non_json_diagnostic(caplog):
    class GatewayResponse(FakeResponse):
        status_code = 502
        def iter_content(self, chunk_size=32768):
            yield b'<html><h1>502 Bad Gateway</h1></html>'
    with pytest.raises(ProviderError):
        _fetch('112592538','es',api_key='test-key',get=lambda *a,**kw:GatewayResponse({}))
    assert 'body_type=non_json' in caplog.text


def test_connection_error_is_diagnostic_and_never_leaks_api_key(caplog):
    import requests
    secret = 'very-private-test-token'
    def fail(*args, **kwargs):
        raise requests.ConnectionError('Failed to connect to https://api.opendata-api.com/?key=' + secret)
    with pytest.raises(ProviderError,match='network or DNS failure') as err:
        _fetch('112592538', 'es', api_key=secret, get=fail)
    assert secret not in str(err.value)
    assert secret not in caplog.text
    assert 'kind=connection' in caplog.text

def test_valid_http_200_but_invalid_json_is_distinguishable(caplog):
    class InvalidResponse(FakeResponse):
        def iter_content(self, chunk_size=32768):
            yield b'<html>200 upstream proxy returned invalid response</html>'
    with pytest.raises(ProviderError,match='HTTP 200.*not valid JSON'):
        _fetch('112592538', 'es', api_key='test-key', get=lambda *a,**kw:InvalidResponse({}))
    assert 'json_parse_failed' in caplog.text


def test_http_200_error_payload_without_adid_is_not_a_mismatch(caplog):
    payload = {"status": "error", "message": "unsafe user@example.com secret-value", "error": "lookup_failed"}
    with pytest.raises(ProviderError, match="without an ad ID") as exc:
        normalize_property(payload, URL)
    assert "mismatch" in str(exc.value)
    assert "property record missing adid" in caplog.text
    assert "status" in caplog.text
    assert "user@example.com" not in caplog.text
    assert "secret-value" not in caplog.text


def test_invalid_ad_id_format_does_not_log_attacker_value(caplog):
    with pytest.raises(ProviderError, match="invalid property ID format"):
        normalize_property({**RECORD, "adid": "secret-token-instead-of-id"}, URL)
    assert "secret-token-instead-of-id" not in caplog.text


def test_true_mismatch_is_logged_as_numeric_ids_only(caplog):
    with pytest.raises(ProviderError, match="different listing ID"):
        normalize_property({**RECORD, "adid": 112592538}, URL)
    assert "requested=113074128" in caplog.text
    assert "returned=112592538" in caplog.text


def test_opendata_data_message_envelope_imports_verified_property():
    # Exact top-level keys observed in Render logs; no network or credits.
    url='https://www.idealista.com/inmueble/112592538/'
    detail={**RECORD, 'adid':112592538}
    wrapped={'data': detail, 'message': 'ok'}
    result=normalize_property(wrapped,url)
    assert result['status']=='imported'
    assert result['fields']['monthly_rent_eur']['value']==1500
    assert result['listing_id']=='112592538'


def test_opendata_multiple_envelopes_and_single_item_array():
    wrapped={'message': 'success', 'data': {'result': [RECORD]}}
    result=normalize_property(wrapped, URL)
    assert result['status']=='imported'
    assert result['fields']['bedrooms']['value']==2


def test_opendata_wrapped_wrong_property_remains_rejected():
    wrapped={'message': 'ok', 'data': {**RECORD, 'adid': 112592538}}
    with pytest.raises(ProviderError, match='different listing ID'):
        normalize_property(wrapped,URL)


def test_opendata_empty_data_envelope_reports_missing_not_mismatch(caplog):
    with pytest.raises(ProviderError, match='empty data field'):
        normalize_property({'data':{},'message':'sensitive arbitrary message'},URL)
    assert 'sensitive arbitrary message' not in caplog.text
    assert 'data_type=dict' in caplog.text


def test_opendata_nested_status_without_property_does_not_create_fake_details():
    with pytest.raises(ProviderError, match='no identifiable property'):
        normalize_property({'data':{'status':'error','message':'no entry'},'message':'failed'},URL)


def test_opendata_direct_record_still_supported():
    assert normalize_property(RECORD, URL)['status']=='imported'