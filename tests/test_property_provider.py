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