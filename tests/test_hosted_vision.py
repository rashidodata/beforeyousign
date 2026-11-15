from io import BytesIO
import json

import pytest
from PIL import Image

from beforeyousign import hosted_vision as hv

LISTING = {
    'listing_id': '112592538', 'status': 'imported',
    'source_url': 'https://www.idealista.com/inmueble/112592538/',
    'photo_urls': [f'https://img4.idealista.com/photo/image{i}.jpg?Expires=123&Signature=X' for i in range(7)],
}
ENV = {'BYS_VISION_API_URL': 'https://vision.example.com/v1/chat/completions',
       'BYS_VISION_API_TOKEN': 'private-token'}


def jpeg_bytes():
    b=BytesIO()
    Image.frombytes('RGB', (200, 200), bytes(((i * 71 + i // 7) % 256 for i in range(200*200*3)))).save(b, 'JPEG', quality=85)
    return b.getvalue()


def test_cache_key_ignores_expiring_signatures():
    a=hv.cache_key('112592538', LISTING['photo_urls'])
    altered=[u.replace('Expires=123&Signature=X','Expires=999&Signature=Y') for u in LISTING['photo_urls']]
    assert a==hv.cache_key('112592538',altered)
    assert len(hv.safe_photo_urls(LISTING))==7


def test_model_host_requires_protected_https_and_token():
    assert hv.model_host_configured(ENV)
    assert not hv.model_host_configured({**ENV, 'BYS_VISION_API_URL':'http://127.0.0.1/v1/chat/completions'})
    assert not hv.model_host_configured({**ENV, 'BYS_VISION_API_TOKEN':''})


def test_all_photos_are_analyzed_but_report_is_one_document():
    calls=[]
    def fake_chat(content, *, env=None, tokens=None):
        calls.append(content)
        if content[0]['type']=='text':
            return json.dumps({
                'summary_es':'Se observan varias estancias y muebles.',
                'summary_en':'Several rooms and furnishings are visible.',
                'visible_strengths_es':['Estancias fotografiadas'],
                'visible_strengths_en':['Rooms photographed'],
                'visible_concerns_es':[], 'visible_concerns_en':[],
                'landlord_questions_es':['¿Estado real?'],
                'landlord_questions_en':['Actual condition?'],
            })
        return 'Visible windows, painted walls, and some furniture. No confirmed hidden issues.'
    result=hv.analyze_listing_images(LISTING,env=ENV,get_image=lambda u:jpeg_bytes(),send=fake_chat)
    assert result['photos_available']==7
    assert result['photos_analyzed']==7
    assert result['status']=='completed'
    assert result['summary_es'].startswith('Se observan')
    assert len(calls)==3 # 4 photos + 3 photos + one combined summary
    assert sum(sum(p['type']=='image_url' for p in call) for call in calls)==7


def test_partial_photo_failures_disclosed():
    def get(url):
        if 'image2.' in url: raise ValueError('unavailable')
        return jpeg_bytes()
    def chat(content, *, env=None, tokens=None):
        if content[0]['type']=='text':
            return json.dumps({'summary_es':'Algunas imágenes disponibles.','summary_en':'Some images available.'})
        return 'A room.'
    result=hv.analyze_listing_images(LISTING,env=ENV,get_image=get,send=chat)
    assert result['photos_analyzed']==6
    assert result['photos_available']==7
    assert result['status']=='partial'


def test_no_model_and_bad_json_fail_safe():
    with pytest.raises(hv.VisionError,match='not configured'):
        hv.analyze_listing_images(LISTING, env={})
    with pytest.raises(hv.VisionError,match='incomplete overall report'):
        hv._parse_summary('maybe a room',analyzed=1,total=1)


def test_request_uses_secret_header_and_no_redirect():
    sent=[]
    class Resp:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'ok'}}]}
    def fake_post(url,**kwargs):
        sent.append((url,kwargs));return Resp()
    value=hv.host_chat([{'type':'text','text':'test'}],env=ENV,post=fake_post)
    assert value=='ok'
    assert sent[0][1]['headers']['Authorization']=='Bearer private-token'
    assert sent[0][1]['allow_redirects'] is False


class FakeRedis:
    def __init__(self):self.store={}
    def get(self,k):return self.store.get(k)
    def set(self,k,v,*,ex=None,nx=False):
        if nx and k in self.store:return False
        self.store[k]=v;return True
    def setex(self,k,ttl,v):self.store[k]=v;return True
    def incr(self,k):
        n=int(self.store.get(k,0))+1;self.store[k]=n;return n
    def expire(self,k,ttl):return True
    def delete(self,k):self.store.pop(k,None)


def test_route_queues_automatically_and_deduplicates(monkeypatch):
    from beforeyousign import hosted_vision_routes as routes
    monkeypatch.setattr(routes,'_authorized',lambda code:True)
    monkeypatch.setattr(routes,'_listing',lambda url:LISTING)
    store=FakeRedis()
    monkeypatch.setattr(routes,'_cache',lambda:store)
    monkeypatch.setattr(routes,'model_host_configured',lambda:True)
    monkeypatch.setenv('BYS_VISION_AUTORUN_ENABLED','1')
    class Tasks:
        def __init__(self):self.jobs=[]
        def add_task(self,f,*args):self.jobs.append((f,args))
    task=Tasks()
    payload=routes.VisionRequest(url=LISTING['source_url'])
    first=routes.start_visual_summary(payload,task,x_bys_pilot_code='abc')
    second=routes.start_visual_summary(payload,task,x_bys_pilot_code='abc')
    assert first['status']=='queued'
    assert second['status']=='queued' # already queued result is reused, never charges twice
    assert len(task.jobs)==1
    assert store.get('bys:hosted-vision:daily:'+routes.datetime.now(routes.timezone.utc).strftime('%Y%m%d'))==1


def test_unconfigured_does_not_enqueue(monkeypatch):
    from beforeyousign import hosted_vision_routes as routes
    monkeypatch.setattr(routes,'_authorized',lambda code:True)
    monkeypatch.setattr(routes,'_listing',lambda url:LISTING)
    monkeypatch.setattr(routes,'model_host_configured',lambda:False)
    class Tasks:
        def add_task(self,*args):raise AssertionError('should not queue')
    out=routes.start_visual_summary(routes.VisionRequest(url=LISTING['source_url']), Tasks(), x_bys_pilot_code='abc')
    assert out['status']=='unconfigured'