from beforeyousign.import_quota import reserve_lookup, QuotaUnavailable
import pytest

class FakeRedis:
    def __init__(self): self.n=0; self.ids=set()
    def eval(self, lua, nkeys, global_key, listing_key, limit, ttl):
        assert 'EXISTS' in lua and 'INCR' in lua
        if listing_key in self.ids: return 2
        if self.n >= limit: return 0
        self.n += 1
        self.ids.add(listing_key)
        return 1


def test_budget_and_dedup():
    redis=FakeRedis()
    env={'BYS_REDIS_URL':'redis://localhost:6379','BYS_PROVIDER_DAILY_LIMIT':'2'}
    assert reserve_lookup('12345',env=env,client=redis)=='allowed'
    assert reserve_lookup('12345',env=env,client=redis)=='already_requested'
    assert reserve_lookup('56789',env=env,client=redis)=='allowed'
    assert reserve_lookup('99999',env=env,client=redis)=='limit_reached'


def test_fail_closed_without_redis():
    with pytest.raises(QuotaUnavailable): reserve_lookup('12345',env={})


def test_fail_closed_on_error():
    class BadRedis:
        def eval(self,*args): raise ConnectionError()
    with pytest.raises(QuotaUnavailable): reserve_lookup('12345',env={'BYS_REDIS_URL':'redis://localhost:6379'},client=BadRedis())