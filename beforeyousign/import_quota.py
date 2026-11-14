"""Fail-closed budget gate for provider lookups (Render Key Value / Redis).

Key Value is volatile on the free tier; this is a short-term spending throttle,
not an authoritative account-level billing cap. Configure a provider-side hard cap.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

class QuotaUnavailable(RuntimeError):
    pass

LUA = '''
local global = KEYS[1]
local listing = KEYS[2]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if redis.call('EXISTS', listing) == 1 then return 2 end
local n = tonumber(redis.call('GET', global) or '0')
if n >= limit then return 0 end
redis.call('INCR', global)
if n == 0 then redis.call('EXPIRE', global, ttl) end
redis.call('SET', listing, '1', 'EX', ttl)
return 1
'''


def reserve_lookup(listing_id: str, *, env=None, client=None) -> str:
    """Reserve max N new listing fetches/day and dedupe same listing by id.

    Returns 'allowed', 'already_requested', or 'limit_reached'. Any quota
    backend error raises QuotaUnavailable, preventing paid provider requests.
    """
    env = os.environ if env is None else env
    url = env.get('BYS_REDIS_URL', '')
    if not url or not url.startswith(('redis://', 'rediss://')):
        raise QuotaUnavailable('Public quota storage has not been configured.')
    try:
        limit = min(max(int(env.get('BYS_PROVIDER_DAILY_LIMIT', '3')), 1), 20)
    except (ValueError, TypeError):
        raise QuotaUnavailable('Invalid configured daily limit.') from None
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    if client is None:
        try:
            import redis
            conn = redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=2)
        except Exception as exc:
            raise QuotaUnavailable("Usage limiter is unavailable.") from exc
    else:
        conn = client
    try:
        state = int(conn.eval(LUA, 2, f'bys:opendata:daily:{day}', f'bys:opendata:listing:{day}:{listing_id}', limit, 90000))
    except Exception as exc:
        raise QuotaUnavailable('Usage limiter is unavailable.') from exc
    return {0:'limit_reached', 1:'allowed', 2:'already_requested'}[state]


def cached_listing(listing_id: str, *, env=None):
    """Return a prior provider response without another billable lookup."""
    env = os.environ if env is None else env
    try:
        import redis, json
        url = env.get('BYS_REDIS_URL','')
        if not url: return None
        r = redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=2)
        raw = r.get('bys:opendata:response:' + listing_id)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_listing(listing_id: str, result: dict, *, env=None) -> None:
    """Best-effort cache; quota reservation is always enforced before any API call."""
    env = os.environ if env is None else env
    try:
        import redis, json
        url = env.get('BYS_REDIS_URL','')
        if not url: return
        r = redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=2)
        r.setex('bys:opendata:response:' + listing_id, 86400, json.dumps(result))
    except Exception:
        return