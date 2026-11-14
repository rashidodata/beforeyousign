from beforeyousign.report_services import (
    listing_photo_urls, approximate_position, parse_nearby, overpass_query,
    fetch_listing_image, review_cache_key, neighborhood_summary,
)
import pytest


def test_provider_location_hidden_is_marked_as_approximate():
    o=approximate_position({'ubication':{'latitude':40.423,'longitude':-3.7,'hasHiddenAddress':True}})
    assert o['approximate'] is True
    assert abs(o['latitude']-40.423)<1e-6
    assert approximate_position({'ubication':{'latitude':None, 'longitude':-3.7}}) is None


def test_gallery_accepts_only_idealista_https():
    o=listing_photo_urls({'multimedia':{'images':[
      {'url':'https://img4.idealista.com/photo/1.jpg'},
      {'url':'http://img4.idealista.com/photo/2.jpg'},
      {'url':'https://evil.example.com/photo.jpg'},
      {'url':'https://img4.idealista.com/photo/1.jpg'},
      {'url':'https://img3.idealista.com/blur/2.jpg'},
    ]}})
    assert o == ['https://img4.idealista.com/photo/1.jpg','https://img3.idealista.com/blur/2.jpg']
    with pytest.raises(ValueError,match='Untrusted'):
        fetch_listing_image('https://127.0.0.1/admin')


def test_grouped_amenities_sorted_nearest_with_usable_links():
    payload={'elements':[
      {'type':'node','id':3,'lat':40.004,'lon':-3,'tags':{'name':'Far Mercadona','shop':'supermarket'}},
      {'type':'node','id':2,'lat':40.001,'lon':-3,'tags':{'name':'Close Dia','shop':'supermarket'}},
      {'type':'node','id':1,'lat':40.0005,'lon':-3,'tags':{'name':'Pharmacy One','amenity':'pharmacy'}},
      {'type':'node','id':5,'lat':40.0001,'lon':-3,'tags':{'shop':'supermarket'}},
      {'type':'node','id':6,'lat':40.001,'lon':-3,'tags':{'name':'Park A','leisure':'park'}},
    ]}
    x=parse_nearby(payload,40,-3)
    assert [e['name'] for e in x['Supermarkets']] == ['Close Dia','Far Mercadona']
    assert x['Supermarkets'][0]['distance_m'] < x['Supermarkets'][1]['distance_m']
    assert x['Pharmacies'][0]['source_url'] == 'https://www.openstreetmap.org/node/1'
    assert x['Parks'][0]['name']=='Park A'
    assert not x['Local markets']


def test_nearby_query_is_fixed_and_bounded():
    s=overpass_query(40.42,-3.70,1200)
    assert '(around:1200,40.420000,-3.700000)' in s
    with pytest.raises(ValueError): overpass_query(100,0,1200)
    with pytest.raises(ValueError): overpass_query(40,-3,5000)


def test_cache_failure_does_not_query_overpass(monkeypatch):
    import beforeyousign.report_services as mod
    monkeypatch.setattr(mod,'redis_connection',lambda:None)
    def forbid(*a,**k): raise AssertionError('Should not hit OSM')
    monkeypatch.setattr(mod.requests,'post',forbid)
    x=neighborhood_summary(40.42,-3.7)
    assert x['status']=='unavailable'


def test_review_key_stable_does_not_expose_url():
    k=review_cache_key('112592538',['https://img3.idealista.com/photo/123.jpg'])
    assert '112592538' in k
    assert 'http' not in k

class _FakeNeighborhoodCache:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True
    def setex(self, key, ttl, value):
        self.data[key] = value
    def delete(self, key):
        self.data.pop(key, None)


class _FakeOverpassResponse:
    def __init__(self, status, data):
        import json
        self.status_code = status
        self.body = data
        self.content = json.dumps(data).encode('utf-8')
    def json(self):
        return self.body


def test_neighborhood_uses_second_provider_after_upstream_503(monkeypatch, caplog):
    import beforeyousign.report_services as mod
    redis = _FakeNeighborhoodCache()
    monkeypatch.setattr(mod, 'redis_connection', lambda: redis)
    calls = []
    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            return _FakeOverpassResponse(503, {})
        return _FakeOverpassResponse(200, {'elements': [
            {'type':'node','id':31,'lat':40.4268,'lon':-3.7028,
             'tags':{'shop':'supermarket','name':'Nearby supermarket'}},
        ]})
    monkeypatch.setattr(mod.requests, 'post', fake_post)
    result = mod.neighborhood_summary(40.4266383, -3.7028469)
    assert result['status'] == 'ok'
    assert result['groups']['Supermarkets'][0]['name'] == 'Nearby supermarket'
    assert len(calls) == 2
    assert calls[0] == 'https://overpass.private.coffee/api/interpreter'
    assert calls[1] == 'https://overpass-api.de/api/interpreter'
    assert 'kind=http status=503' in caplog.text
    assert mod.neighborhood_summary(40.4266383, -3.7028469)['status'] == 'ok'
    assert len(calls) == 2  # Served from cache, no unnecessary external lookup.


def test_neighborhood_respects_429_and_caches_failed_query(monkeypatch):
    import beforeyousign.report_services as mod
    cache = _FakeNeighborhoodCache()
    monkeypatch.setattr(mod, 'redis_connection', lambda: cache)
    calls = []
    def fake_post(url, **kw):
        calls.append(url)
        return _FakeOverpassResponse(429,{})
    monkeypatch.setattr(mod.requests,'post',fake_post)
    result = mod.neighborhood_summary(40.4266383,-3.7028469)
    assert result['status']=='unavailable'
    assert len(calls)==1  # Do not bypass the rate limit using the other server.
    assert mod.neighborhood_summary(40.4266383,-3.7028469)['status']=='unavailable'
    assert len(calls)==1


def test_neighborhood_rejects_overpass_error_remark_even_with_http_200(monkeypatch):
    import beforeyousign.report_services as mod
    monkeypatch.setattr(mod,'redis_connection',_FakeNeighborhoodCache)
    calls=[]
    def fake_post(url, **kw):
        calls.append(url)
        return _FakeOverpassResponse(200,{'remark':'runtime error: query timed out','elements':[]})
    monkeypatch.setattr(mod.requests,'post',fake_post)
    result=mod.neighborhood_summary(40.4266383,-3.7028469)
    assert result['status']=='unavailable'
    assert len(calls)==1  # A more expensive retry is inappropriate.