import os
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from beforeyousign.market_routes import CompareRequest, market_comparables_endpoint, _safe_page
from beforeyousign.market import search_parameters,search_cache_key
from test_market import SUBJECT,_row

class FakeCache:
    def __init__(self):self.data={};self.budget={}
    def get(self,k):return self.data.get(k)
    def set(self,k,v,**kwargs):
        if kwargs.get('nx') and k in self.data:return False
        self.data[k]=v;return True
    def delete(self,k):self.data.pop(k,None)
    def incr(self,k):self.budget[k]=self.budget.get(k,0)+1;return self.budget[k]
    def expire(self,k,s):pass
    def setex(self,k,s,v):self.data[k]=v

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('BYS_PUBLIC_IMPORT_ENABLED','1')
    monkeypatch.setenv('BYS_PILOT_ACCESS_CODE','private-code')
    monkeypatch.delenv('BYS_MARKET_SEARCH_ENABLED',raising=False)
    monkeypatch.delenv('BYS_MARKET_USAGE_CONFIRMED',raising=False)
    monkeypatch.setattr('beforeyousign.import_quota.cached_listing',lambda k: SUBJECT)
    cache=FakeCache()
    monkeypatch.setattr('beforeyousign.market_routes._cache_instance',lambda: cache)
    return cache

def test_requires_auth():
    with pytest.raises(HTTPException) as e:
        market_comparables_endpoint(CompareRequest(url=SUBJECT['source_url']),x_bys_pilot_code='bad')
    assert e.value.status_code==401

def test_no_spend_before_explicit_confirmation(env,monkeypatch):
    def forbid(*a,**k):raise AssertionError('Paid search should not run')
    monkeypatch.setattr('beforeyousign.market_routes.fetch_provider_comparables',forbid)
    x=market_comparables_endpoint(CompareRequest(url=SUBJECT['source_url']),x_bys_pilot_code='private-code')
    assert x['status']=='confirmation_required'
    assert x['benchmark']['eur_sqm']==26.9
    y=market_comparables_endpoint(CompareRequest(url=SUBJECT['source_url'],approve_provider_search=True),x_bys_pilot_code='private-code')
    assert y['status']=='not_enabled'

def test_one_search_when_enabled_then_cached(env,monkeypatch):
    monkeypatch.setenv('BYS_MARKET_SEARCH_ENABLED','1');monkeypatch.setenv('BYS_MARKET_USAGE_CONFIRMED','1')
    monkeypatch.setenv('BYS_OPENDATA_API_KEY','fake-test-key')
    calls=[]
    def fake(key,params):
        calls.append(params)
        return {'data':{'elementList':[_row(i,lat_diff=.001,price=1500+i*20) for i in range(6)]}}
    monkeypatch.setattr('beforeyousign.market_routes.fetch_provider_comparables',fake)
    p=CompareRequest(url=SUBJECT['source_url'],approve_provider_search=True)
    a=market_comparables_endpoint(p,x_bys_pilot_code='private-code')
    b=market_comparables_endpoint(p,x_bys_pilot_code='private-code')
    assert a['status']=='searched' and b['status']=='cached'
    assert len(calls)==1 and a['comparison']['eligible_count']==6
    assert not any('contactInfo' in str(k) for k in env.data.values())

def test_search_cache_sanitizes_personal_info():
    p=_safe_page({'elementList':[{'propertyCode':11222,'operation':'rent','price':1600,'size':80,
            'contactInfo':{'email':'personal@example.com'},'description':'private user content'}]})
    assert 'contactInfo' not in p['elementList'][0]
    assert 'description' not in p['elementList'][0]