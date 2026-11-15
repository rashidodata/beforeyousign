import copy
import pytest
from beforeyousign.market import (
    benchmark_for_listing,find_madrid_market_area,search_parameters,search_cache_key,
    comparables_from_search,fetch_provider_comparables, MarketProviderError
)

SUBJECT={'status':'imported','listing_id':'112592538','source_url':'https://www.idealista.com/inmueble/112592538/',
 'listing_operation':'rent','market_location_id':'0-EU-ES-28-07-001-079',
 'map_pin':{'latitude':40.4266383,'longitude':-3.7028469,'approximate':True},
 'fields':{'monthly_rent_eur':{'value':1800},'area_sqm':{'value':75},
           'bedrooms':{'value':2},'property_type':{'value':'flat'},
           'city_or_area':{'value':'Barrio Malasaña-Universidad, Madrid'}}}

def test_market_benchmark_real_malasana():
    b=benchmark_for_listing(SUBJECT)
    assert b['market_area']=='Malasaña-Universidad'
    assert b['eur_sqm']==26.9 and b['source_date']=='2026-10'
    assert b['listing_eur_sqm']==24 and b['position']=='near_area'

def test_no_getafe_universidad_leak():
    a=find_madrid_market_area('Universidad, Getafe, Madrid')
    assert a is None
    assert benchmark_for_listing({**SUBJECT,'fields':{**SUBJECT['fields'],'city_or_area':{'value':'Barcelona'}}})['status']=='unavailable'

def test_district_benchmark_precise_and_unknown_area():
    a=find_madrid_market_area('Chamberí, Madrid');assert a['eur_sqm']==26.3
    a=find_madrid_market_area('Madrid');assert a['eur_sqm']==23.4
    a=find_madrid_market_area('La Latina, Madrid');assert a['level']=='city' # don't mistake barrio for large district

def test_search_parameters_only_when_safe():
    p=search_parameters(SUBJECT)
    assert p['operation']=='rent' and p['maxItems']=='40' and p['numPage']=='1'
    assert p['locationId']=='0-EU-ES-28-07-001-079'
    assert search_cache_key(p)==search_cache_key(dict(p))
    assert search_parameters({**SUBJECT,'market_location_id':'not valid!'}) is None
    assert search_parameters({**SUBJECT,'listing_operation':'sale'}) is None

def _row(i,lat_diff=0.001,price=1600,size=75,rooms=2,**extra):
    return {'propertyCode':110000000+i,'operation':'rent','price':price,'size':size,'rooms':rooms,
            'propertyType':'flat','latitude':40.4266383+lat_diff,'longitude':-3.7028469,**extra}

def test_comparables_filter_deduplicate_verify_distances():
    records=[_row(i,lat_diff=(i+1)*0.0004,price=1400+25*i,size=70+2*i) for i in range(8)]
    records.extend([records[0],_row(11,lat_diff=.3),_row(12,size=200),
                    _row(13,price=0),_row(14,shortTerm=True),_row(15,latitude=None)])
    x=comparables_from_search(SUBJECT,{'elementList':records})
    assert x['eligible_count']==8 and x['status']=='available' and x['confidence']=='low'
    assert all('/inmueble/' in c['url'] for c in x['comparable_listings'])
    assert x['range_eur_sqm'][0]<x['range_eur_sqm'][1]
    assert x['difference_pct']>0

def test_small_sample_no_verdict_and_no_fake_comps():
    records=[_row(1),_row(2),_row(3)]
    x=comparables_from_search(SUBJECT,{'elementList':records})
    assert x['status']=='insufficient' and x['position']=='no_verdict'
    assert x['median_equivalent_rent_eur']>0
    with pytest.raises(ValueError): comparables_from_search(SUBJECT,{'error':'hello'})

def test_zero_valid_no_stats():
    x=comparables_from_search(SUBJECT,{'data':{'elementList':[_row(1,lat_diff=.15)]}})
    assert x['eligible_count']==0 and 'median_eur_sqm' not in x

def test_one_external_call_and_http_errors():
    calls=[]
    class Fake:
        status_code=200
        def __enter__(self): return self
        def __exit__(self,*args):pass
        def iter_content(self,chunk_size=32768):yield b'{"data":{"elementList":[]}}'
    def get(url,**kw):calls.append((url,kw));return Fake()
    payload=fetch_provider_comparables('test-key',search_parameters(SUBJECT),get)
    assert payload['data']['elementList']==[]
    assert len(calls)==1 and calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['params']['operation']=='rent'
    class Bad(Fake):status_code=402
    with pytest.raises(MarketProviderError,match='HTTP 402'):
        fetch_provider_comparables('secret',search_parameters(SUBJECT),lambda *a,**kw:Bad())