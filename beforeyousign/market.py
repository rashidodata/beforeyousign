"""Evidence-led rental asking-price context and opt-in comparable searches.

This module never contacts Idealista directly. Only an operator-approved,
third-party search (one page) may be made after an explicit user action.
The public benchmark is a dated, manually reviewed press-report snapshot;
it must never be represented as a comparable-property valuation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from math import asin, ceil, cos, floor, isfinite, radians, sin, sqrt
from statistics import median
from typing import Any
import re
import unicodedata

import requests

MARKET_SOURCE_DATE = '2026-10'
MADRID_SOURCE = 'https://www.idealista.com/sala-de-prensa/informes-precio-vivienda/alquiler/madrid-comunidad/madrid-provincia/madrid/'
CENTRO_SOURCE = MADRID_SOURCE + 'centro/'
SEARCH_ENDPOINT = 'https://api.opendata-api.com/api/project/idealista/list-home-properties'
MADRID_CITY_LOCATION_ID = '0-EU-ES-28-07-001-079'

# Manually verified October 2026 values from Idealista's public asking-rent report.
MADRID_DISTRICTS = {
    'arganzuela': 22.4, 'barajas': 18.1, 'barrio de salamanca': 28.4,
    'carabanchel': 19.2, 'centro': 26.5, 'chamartin': 23.7,
    'chamberi': 26.3, 'ciudad lineal': 20.2, 'fuencarral': 19.1,
    'hortaleza': 19.6, 'latina': 19.3, 'moncloa': 21.6,
    'moratalaz': 17.9, 'puente de vallecas': 19.3, 'retiro': 23.7,
    'san blas': 17.9, 'tetuan': 23.0, 'usera': 20.1,
    'vicalvaro': 17.7, 'villa de vallecas': 17.3, 'villaverde': 18.3,
}
CENTRO_BARRIOS = {
    'malasana-universidad': 26.9, 'chueca-justicia': 28.6,
    'huertas-cortes': 26.9, 'lavapies-embajadores': 25.7,
    'palacio': 25.0, 'sol': 25.6,
}
ALIASES = {
    'malasana-universidad': ('malasana', 'universidad'),
    'chueca-justicia': ('chueca', 'justicia'),
    'huertas-cortes': ('huertas', 'cortes'),
    'lavapies-embajadores': ('lavapies', 'embajadores'),
    'palacio': ('palacio',), 'sol': ('sol',),
}
DISTRICT_ALIASES = {
    'barrio de salamanca': ('barrio de salamanca', 'distrito salamanca', 'salamanca'),
    'san blas': ('san blas',), 'villa de vallecas': ('villa de vallecas',),
    'puente de vallecas': ('puente de vallecas',), 'ciudad lineal': ('ciudad lineal',),
    'fuencarral': ('fuencarral',), 'moncloa': ('moncloa',),
    **{k: (k,) for k in MADRID_DISTRICTS if k not in {'barrio de salamanca','san blas','villa de vallecas','puente de vallecas','ciudad lineal','fuencarral','moncloa'}},
}


def _fold(s: Any) -> str:
    text = unicodedata.normalize('NFKD', str(s or '').casefold())
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('–','-').replace('—','-')


def _match_token(text: str, token: str) -> bool:
    return re.search(r'(?<![a-z0-9])' + re.escape(token) + r'(?![a-z0-9])', text) is not None


def _finite_number(raw: Any, lo: float, hi: float) -> float | None:
    if raw is None or isinstance(raw,bool): return None
    if isinstance(raw, dict): raw=raw.get('amount',raw.get('value'))
    try: n=float(raw)
    except (ValueError,TypeError,OverflowError): return None
    return n if isfinite(n) and lo<=n<=hi else None


def find_madrid_market_area(location: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Use the most specific *supported* known area, never fuzzy-match another city."""
    context = context if isinstance(context,dict) else {}
    city = _fold(context.get('city',''))
    full = _fold(' '.join(str(x or '') for x in (location,context.get('city'),context.get('district'),context.get('neighborhood'))))
    if not (_match_token(full,'madrid') or city=='madrid'):
        return None
    if any(_match_token(full,k) for k in ('getafe','alcobendas','alcorcon','mostoles','leganes','fuenlabrada')):
        return None
    neighborhood=_fold(context.get('neighborhood',''))
    district=_fold(context.get('district',''))
    # Prefer explicit barrio or recognizable Idealista barrio label.
    for key, value in CENTRO_BARRIOS.items():
        aliases=ALIASES.get(key,(key,))
        if _match_token(full,key) or _match_token(neighborhood,key) or any(_match_token(neighborhood,a) for a in aliases):
            return dict(label=key.title().replace('Malasana','Malasaña').replace('Lavapies','Lavapiés'),level='neighborhood',eur_sqm=value,source_url=CENTRO_SOURCE)
        if any(_match_token(full,a) for a in aliases) and (('centro' in full) or 'barrio' in full or 'malasana' in full or 'chueca' in full or 'lavapies' in full or 'huertas' in full):
            return dict(label=key.title().replace('Malasana','Malasaña').replace('Lavapies','Lavapiés'),level='neighborhood',eur_sqm=value,source_url=CENTRO_SOURCE)
    # Avoid mistaking 'la latina' the neighbourhood for Distrito Latina.
    for key in sorted(MADRID_DISTRICTS,key=len,reverse=True):
        if key=='latina' and (_match_token(full,'la latina') or _match_token(full,'barrio la latina')):
            continue
        aliases=DISTRICT_ALIASES[key]
        if any(_match_token(district,a) for a in aliases) or any(_match_token(full,a) for a in aliases):
            return dict(label=key.title().replace('Chamberi','Chamberí').replace('Tetu an','Tetuán').replace('Tetuan','Tetuán').replace('Vicalvaro','Vicálvaro').replace('Chamartin','Chamartín'),level='district',eur_sqm=MADRID_DISTRICTS[key],source_url=MADRID_SOURCE)
    return dict(label='Madrid',level='city',eur_sqm=23.4,source_url=MADRID_SOURCE)


def benchmark_for_listing(listing: dict[str,Any]) -> dict[str,Any]:
    fields=listing.get('fields') or {}
    loc=fields.get('city_or_area') or {}
    label=loc.get('value') if isinstance(loc,dict) else ''
    area=find_madrid_market_area(label or '', listing.get('market_area'))
    rent=_finite_number((fields.get('monthly_rent_eur') or {}).get('value'),100,100000)
    sqm=_finite_number((fields.get('area_sqm') or {}).get('value'),8,20000)
    if area is None:
        return {'status':'unavailable','reason':'No verified published area benchmark is configured for this location.','source_date':MARKET_SOURCE_DATE}
    benchmark={
        'status':'available', 'market_area':area['label'],'geography_level':area['level'],
        'eur_sqm':area['eur_sqm'],'source_date':MARKET_SOURCE_DATE,
        'source_name':'idealista published asking-rent report', 'source_url':area['source_url'],
        'method':'area_asking_rent_headline',
        'caveat':'Published area-wide asking-rent statistic, not a sample of comparable apartments or a fair-value estimate.',
        'listing_eur_sqm':round(rent/sqm,2) if rent and sqm else None,
        'deviation_pct':round(((rent/sqm)/area['eur_sqm']-1)*100,1) if rent and sqm else None,
        'area_implied_monthly_eur':round(area['eur_sqm']*sqm) if sqm else None,
    }
    delta=benchmark['deviation_pct']
    benchmark['position']=('not_comparable' if delta is None else 'above_area' if delta>12 else 'below_area' if delta<-12 else 'near_area')
    return benchmark


def enrich_listing_market(listing:dict[str,Any])->dict[str,Any]:
    # No extra provider request; works for already-cached listings.
    if listing.get('status')!='imported': return listing
    return {**listing,'market_benchmark':benchmark_for_listing(listing)}


def location_id_from_listing(listing:dict[str,Any])->str|None:
    text=listing.get('market_location_id')
    if not isinstance(text,str) or not re.fullmatch(r'[0-9A-Za-z-]{6,110}',text): return None
    # No arbitrary user-supplied URL; use only the validated provider location ID.
    return text


def search_parameters(listing:dict[str,Any]) -> dict[str,str] | None:
    lid=location_id_from_listing(listing)
    fields=listing.get('fields') or {}
    size=_finite_number((fields.get('area_sqm') or {}).get('value'),12,2000)
    if not lid or not size or listing.get('listing_operation') not in ('rent','rental','alquiler'):return None
    bucket=max(20,round(size/10)*10)
    # Deliberately broad provider filter, followed by stricter local comparison.
    return {'locationId':lid,'location':'es','locale':'es','operation':'rent','order':'mostrecent',
            'maxItems':'40','numPage':'1','minSize':str(max(10,floor(bucket*.65))),
            'maxSize':str(ceil(bucket*1.35))}


def search_cache_key(params:dict[str,str]) ->str:
    key='|'.join(params[k] for k in ('locationId','location','operation','order','maxItems','numPage','minSize','maxSize'))
    return 'bys:market:search:v1:'+sha256(key.encode()).hexdigest()[:32]


def distance_m(a:float,b:float,c:float,d:float)->int:
    r=6371000
    dp=radians(c-a); dl=radians(d-b)
    x=sin(dp/2)**2+cos(radians(a))*cos(radians(c))*sin(dl/2)**2
    return round(2*r*asin(min(1,sqrt(x))))


def _numeric_id(value:Any)->str|None:
    v=str(value or '')
    return v if re.fullmatch(r'[0-9]{5,14}',v) else None


def _listing_group(kind:str)->str:
    text=_fold(kind)
    if any(s in text for s in ('chalet','villa','house','casa','detached')):return 'house'
    if any(s in text for s in ('room','habitacion','bedroom rental')):return 'room'
    return 'flat'


def _is_temporary(row:dict[str,Any])->bool:
    feat=row.get('features') or {}
    return bool(row.get('shortTerm') is True or (isinstance(feat,dict) and feat.get('shortTerm') is True) or
                _fold(row.get('rentalType','')) in ('seasonal','temporary','shortterm','temporada'))


def _quantile(values:list[float],p:float)->float:
    v=sorted(values); pos=(len(v)-1)*p;lo=floor(pos);hi=ceil(pos)
    return v[lo]*(hi-pos)+v[hi]*(pos-lo) if lo!=hi else v[lo]


def comparables_from_search(listing:dict[str,Any],response:dict[str,Any],*,max_distance_m:int=2000)->dict[str,Any]:
    """Filter one real provider page, dedup and calculate transparent statistics."""
    if not isinstance(response,dict):raise ValueError('Unexpected provider search response.')
    payload=response.get('data') if isinstance(response.get('data'),dict) else response
    rows=payload.get('elementList')
    if not isinstance(rows,list):raise ValueError('Provider returned no listing search list.')
    subject_id=_numeric_id(listing.get('listing_id'))
    fields=listing.get('fields') or {}
    sub_rent=_finite_number((fields.get('monthly_rent_eur') or {}).get('value'),100,100000)
    sub_area=_finite_number((fields.get('area_sqm') or {}).get('value'),12,2000)
    sub_rooms=_finite_number((fields.get('bedrooms') or {}).get('value'),0,30)
    sub_type=_listing_group((fields.get('property_type') or {}).get('value',''))
    pin=listing.get('map_pin') or {}
    lat=_finite_number(pin.get('latitude'),-90,90)
    lon=_finite_number(pin.get('longitude'),-180,180)
    if not subject_id or not sub_area or not sub_rent or lat is None or lon is None: 
        return {'status':'insufficient','eligible_count':0,'reason':'Comparable rent, size or approximate map pin is unavailable.'}
    unique:set[str]=set()
    eligible=[]
    for card in rows[:40]:
        if not isinstance(card,dict):continue
        cid=_numeric_id(card.get('propertyCode') or card.get('adid') or card.get('propertyId'))
        if not cid or cid==subject_id or cid in unique:continue
        if _fold(card.get('operation','rent')) not in ('rent','rental','alquiler'):continue
        if _is_temporary(card):continue
        row_type=_listing_group(card.get('propertyType',''))
        if row_type!=sub_type:continue
        rent=_finite_number(card.get('price'),100,100000)
        size=_finite_number(card.get('size'),12,2000)
        if rent is None or size is None or abs(size/sub_area-1)>.25:continue
        rooms=_finite_number(card.get('rooms'),0,30)
        if sub_rooms is not None and rooms is not None and abs(rooms-sub_rooms)>1:continue
        clat=_finite_number(card.get('latitude'),-90,90)
        clon=_finite_number(card.get('longitude'),-180,180)
        if clat is None or clon is None:continue  # no invented distances
        dist=distance_m(lat,lon,clat,clon)
        if dist>max_distance_m:continue
        unique.add(cid)
        eligible.append({'listing_id':cid,'url':f'https://www.idealista.com/inmueble/{cid}/',
                         'rent_eur':round(rent),'area_sqm':round(size,1),
                         'eur_sqm':round(rent/size,2), 'bedrooms':int(rooms) if rooms is not None else None,
                         'distance_m':dist})
    eligible.sort(key=lambda r:r['distance_m'])
    count=len(eligible)
    base={'status':'available' if count>=5 else 'insufficient', 'eligible_count':count,
          'returned_count':len(rows),'comparison_basis':'one page of current advertised rental listings',
          'search_radius_m':max_distance_m,'size_tolerance_pct':25,
          'location_precision':'approximate' if pin.get('approximate') else 'advertised_pin',
          'comparable_listings':eligible[:20],
          'note':'Advertised asking rents only; approximate straight-line distances; results may omit other available listings. No condition adjustment.'}
    if count<3:
        base.update(reason='Fewer than three eligible nearby listings were returned; no price verdict.')
        return base
    vals=[v['rent_eur']/v['area_sqm'] for v in eligible]
    med=median(vals)
    q1,q3=_quantile(vals,.25),_quantile(vals,.75)
    delta=(sub_rent/sub_area/med-1)*100
    base.update(median_eur_sqm=round(med,2),range_eur_sqm=[round(q1,2),round(q3,2)],
                median_equivalent_rent_eur=round(med*sub_area), difference_pct=round(delta,1),
                monthly_difference_eur=round(sub_rent-med*sub_area))
    if count<5:
        base.update(position='no_verdict',confidence='insufficient',reason='At least five eligible listings are required for a directional verdict.')
    else:
        base.update(position='above_comparables' if delta>12 else 'below_comparables' if delta<-12 else 'near_comparables',
                    confidence='low' if count<8 or pin.get('approximate') else 'medium' if count<15 else 'high')
    return base


class MarketProviderError(RuntimeError): pass


def fetch_provider_comparables(api_key:str,params:dict[str,str],get=None)->dict[str,Any]:
    """Exactly one external request, bounded, no redirects or secrets in errors."""
    requester=get or requests.get
    try:
        with requester(SEARCH_ENDPOINT,params={'key':api_key,**params},timeout=(5,26),allow_redirects=False,
                       stream=True,headers={'Accept':'application/json','User-Agent':'BeforeYouSign/market-pilot'}) as resp:
            if resp.status_code!=200:raise MarketProviderError(f'OpenData market-search HTTP {int(resp.status_code)}; the request may have been charged.')
            chunks=[];total=0
            for chunk in resp.iter_content(chunk_size=32768):
                total+=len(chunk)
                if total>4_000_000:raise MarketProviderError('Market provider returned an oversized response.')
                chunks.append(chunk)
        import json
        data=json.loads(b''.join(chunks))
        if not isinstance(data,dict):raise ValueError('non-object JSON')
        return data
    except MarketProviderError:raise
    except (requests.RequestException,ValueError) as exc:
        raise MarketProviderError('The market-search provider failed or returned invalid JSON; it may have charged this lookup.') from exc