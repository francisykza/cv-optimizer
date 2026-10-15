from datetime import date

import pytest
from app.services.llm.base import RateLimitInfo

from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard, QuotaExhaustedError, estimate_tokens


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def limiter(t: FakeTime, tpm: int = 6000, max_wait: float = 60) -> AdaptiveLimiter:
    return AdaptiveLimiter(tokens_per_minute=tpm, max_wait_s=max_wait, clock=t.clock, sleep=t.sleep)


async def test_local_window_waits_until_oldest_call_expires() -> None:
    t = FakeTime()
    lim = limiter(t)
    await lim.acquire(4000)
    t.now += 10
    await lim.acquire(4000)  # 8000 > 6000: espera a que caduque la primera (50 s)
    assert t.sleeps == [pytest.approx(50.05)]


async def test_first_call_larger_than_the_limit_is_allowed() -> None:
    t = FakeTime()
    await limiter(t, tpm=1000).acquire(5000)
    assert t.sleeps == []


async def test_headers_override_the_local_estimate() -> None:
    t = FakeTime()
    lim = limiter(t, tpm=100_000)
    await lim.acquire(1000)
    lim.observe(RateLimitInfo(remaining_tokens=500, reset_tokens_s=7.5, limit_tokens=8000), used_tokens=1200)
    assert lim.tokens_per_minute == 8000  # adopta el límite real
    await lim.acquire(900)  # no caben 900 en los 500 restantes: espera al reset
    assert t.sleeps == [pytest.approx(7.55)]


async def test_daily_request_quota_raises_instead_of_waiting_hours() -> None:
    t = FakeTime()
    lim = limiter(t)
    lim.observe(RateLimitInfo(remaining_requests=0, reset_requests_s=3 * 3600))
    with pytest.raises(QuotaExhaustedError) as exc:
        await lim.acquire(100)
    assert exc.value.reason == "rate_limit" and exc.value.wait_s > 3600 and t.sleeps == []


async def test_after_a_429_it_waits_for_retry_after() -> None:
    t = FakeTime()
    lim = limiter(t)
    lim.observe_rate_limited(20)
    await lim.acquire(100)
    assert t.sleeps == [pytest.approx(20.05)]
    lim.observe_rate_limited(600)
    with pytest.raises(QuotaExhaustedError):
        await lim.acquire(100)


async def test_observe_replaces_estimate_with_real_usage() -> None:
    t = FakeTime()
    lim = limiter(t)
    await lim.acquire(5000)
    lim.observe(None, used_tokens=1000)
    await lim.acquire(4000)  # 1000 reales + 4000 caben en 6000
    assert t.sleeps == []


def test_estimate_tokens() -> None:
    assert estimate_tokens("a" * 350) == 101


def test_budget_guard(repo) -> None:
    today = date(2026, 10, 16)
    guard = BudgetGuard(repo, 1000, today=lambda: today)
    guard.add(600)
    guard.add(300)
    assert guard.used() == 900 and guard.remaining() == 100
    guard.check(100)
    with pytest.raises(QuotaExhaustedError):
        guard.check(101)
    tomorrow = BudgetGuard(repo, 1000, today=lambda: date(2026, 10, 17))
    assert tomorrow.used() == 0
    BudgetGuard(repo, 0, today=lambda: today).check(10**9)  # 0 = sin tope
