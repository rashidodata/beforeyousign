"""Private market comparison API. Disabled until a separate provider search is approved.

No extra property-details lookup. Only an explicit opt-in browser action can
trigger one market-search request; cached regional search results are shared.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from beforeyousign.market import (
    MarketProviderError, comparables_from_search, enrich_listing_market,
    fetch_provider_comparables, search_cache_key, search_parameters,
)

LOG = logging.getLogger('beforeyousign.market_routes')
router = APIRouter()


class CompareRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000)
    approve_provider_search: bool = False


def _preview_authorized(supplied: str | None) -> bool:
    expected=os.getenv('BYS_PILOT_ACCESS_CODE','')
    return bool(os.getenv('BYS_PUBLIC_IMPORT_ENABLED')=='1' and expected and supplied
                and secrets.compare_digest(expected,supplied))


def _safe_page(response: dict[str, Any]) -> dict[str, Any]:
    """Cache only the minimum advertised listing fields, never contact details."""
    payload = response.get('data') if isinstance(response.get('data'),dict) else response
    records=payload.get('elementList')
    if not isinstance(records,list):raise MarketProviderError('Provider returned no recognizable listing search results.')
    keys=('propertyCode','adid','propertyId','operation','price','size','rooms','propertyType',
          'latitude','longitude','rentalType','shortTerm')
    reduced=[]
    for row in records[:40]:
        if isinstance(row,dict):
            card={k:row[k] for k in keys if k in row and isinstance(row[k],(str,int,float,bool,type(None),dict))}
            # Keep only one tested boolean from features, no free-text contact details.
            feat=row.get('features')
            if isinstance(feat,dict) and isinstance(feat.get('shortTerm'),bool):
                card['features']={'shortTerm':feat['shortTerm']}
            reduced.append(card)
    return {'elementList':reduced}


def _cache_instance():
    from beforeyousign.report_services import redis_connection
    return redis_connection()


@router.post('/api/market/comparables')
def market_comparables_endpoint(payload: CompareRequest,
                                x_bys_pilot_code: str | None = Header(default=None)) -> dict[str,Any]:
    if not _preview_authorized(x_bys_pilot_code):
        raise HTTPException(status_code=401,detail='Private preview access code required.')
    from beforeyousign.listings import parse_idealista_url
    from beforeyousign.import_quota import cached_listing
    try:
        listing_id=parse_idealista_url(payload.url)['listing_id']
    except ValueError as exc:
        raise HTTPException(status_code=422,detail='Invalid Idealista rental link.') from exc
    listing=cached_listing(listing_id)
    if not isinstance(listing,dict) or listing.get('status')!='imported' or listing.get('source_url')!=payload.url:
        return {'status':'missing_listing','message':'Import the property first. This comparison never re-fetches paid property details.'}
    listing=enrich_listing_market(listing)
    base={'benchmark':listing['market_benchmark'],'listing_id':listing_id}
    params=search_parameters(listing)
    if not params:
        return {**base,'status':'missing_location','message':'The existing imported property lacks a reliable Idealista search-area ID or usable area. No paid lookup was made.'}
    cache=_cache_instance()
    if cache is None:
        return {**base,'status':'unavailable','message':'Comparison cache is unavailable. No provider search was made.'}
    key=search_cache_key(params)
    try:
        raw=cache.get(key)
        if raw:
            saved=json.loads(raw)
            if isinstance(saved,dict) and isinstance(saved.get('elementList'),list):
                return {**base,'status':'cached','source':'opendata','comparison':comparables_from_search(listing,saved)}
    except Exception:
        return {**base,'status':'unavailable','message':'Comparison cache is temporarily unavailable; no paid lookup was made.'}
    if not payload.approve_provider_search:
        return {**base,'status':'confirmation_required','message':'A new rental-market search can use an additional paid provider request.'}
    # New provider endpoint, new budget. Independent of unlimited property-details imports.
    if not (os.getenv('BYS_MARKET_SEARCH_ENABLED')=='1' and
            os.getenv('BYS_MARKET_USAGE_CONFIRMED')=='1' and
            os.getenv('BYS_OPENDATA_API_KEY','').strip()):
        return {**base,'status':'not_enabled','message':'Automatic comparable searches are not activated until provider pricing and usage rights are confirmed. No token was spent.'}
    lock=key+':busy'
    try:
        locked=cache.set(lock,'1',nx=True,ex=100)
        if not locked:
            return {**base,'status':'loading','message':'A comparison search for this area is already running; retry shortly without additional charges.'}
    except Exception:
        return {**base,'status':'unavailable','message':'Comparison cache is temporarily unavailable; no paid lookup was made.'}
    try:
        # Recheck after acquiring the lock to reduce double payment in parallel requests.
        raw=cache.get(key)
        if raw:
            saved=json.loads(raw)
            if isinstance(saved,dict) and isinstance(saved.get('elementList'),list):
                return {**base,'status':'cached','source':'opendata','comparison':comparables_from_search(listing,saved)}
        max_per_day=min(max(int(os.getenv('BYS_MARKET_DAILY_LIMIT','5')),1),100)
        date=datetime.now(timezone.utc).strftime('%Y%m%d')
        budget='bys:market:daily:'+date
        try:
            used=int(cache.incr(budget))
            if used==1:cache.expire(budget,90000)
        except Exception:
            return {**base,'status':'unavailable','message':'Comparison budget cannot be verified; no provider search was made.'}
        if used>max_per_day:
            return {**base,'status':'daily_limit','message':'The separate market-search budget is exhausted for today. Property lookups are unaffected.'}
        try:
            response=fetch_provider_comparables(os.environ['BYS_OPENDATA_API_KEY'],params)
            safe=_safe_page(response)
        except MarketProviderError as exc:
            LOG.warning('OpenData comparative search failed: kind=provider_error')
            return {**base,'status':'provider_error','message':str(exc)}
        try:
            cache.setex(key,86400,json.dumps(safe))
        except Exception:
            LOG.warning('Market comparison cache save failed')
        return {**base,'status':'searched','source':'opendata','comparison':comparables_from_search(listing,safe)}
    except Exception:
        LOG.exception('Unexpected market comparison error; no secret contents in log')
        return {**base,'status':'unavailable','message':'Unable to finish the market comparison.'}
    finally:
        try:cache.delete(lock)
        except Exception:pass