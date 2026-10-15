import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from hunter.rules.schema import GoldenRules, RssFeed
from hunter.sources import breaker
from hunter.sources.base import FetchResult, JobSource, SourceBlockedError, SourceError, run_source
from hunter.sources.feeds import ArbeitnowSource, RemotiveSource, RssSource
from hunter.sources.jobspy_source import JobspySource, row_to_raw
from hunter.sources.registry import build_sources
from hunter.store.repository import Repository, SourceHealth
from tests.conftest import FIXTURES

NOW = datetime(2026, 10, 15, 8, 30, tzinfo=UTC)
POLICY = breaker.BreakerPolicy(threshold=3, cooldown_h=6, max_cooldown_h=48)


class FakeSource(JobSource):
    def __init__(self, name: str, behaviour: str, jobs: list | None = None) -> None:
        self.name = name
        self.behaviour = behaviour
        self.jobs = jobs or []
        self.calls = 0

    async def fetch(self, rules: GoldenRules) -> FetchResult:
        self.calls += 1
        if self.behaviour == "blocked":
            raise SourceBlockedError("HTTP 429", code="HTTP_429")
        if self.behaviour == "error":
            raise SourceError("boom")
        if self.behaviour == "crash":
            raise RuntimeError("bug inesperado")
        if self.behaviour == "slow":
            await asyncio.sleep(5)
        return FetchResult(jobs=self.jobs, fetched=len(self.jobs))


# --- Aislamiento y timeouts -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("behaviour", "status", "code"),
    [
        ("blocked", "blocked", "HTTP_429"),
        ("error", "error", "SOURCE_ERROR"),
        ("crash", "error", "RuntimeError"),
        ("slow", "timeout", "TIMEOUT"),
        ("ok", "empty", None),
    ],
)
async def test_run_source_never_raises(repo: Repository, rules: GoldenRules, behaviour, status, code) -> None:
    run, jobs = await run_source(FakeSource("x", behaviour), rules, repo, NOW, timeout_s=0.05, policy=POLICY)
    assert run.status == status
    assert run.error_code == code
    assert jobs == []


async def test_one_failing_source_does_not_stop_the_others(repo, rules, make_raw) -> None:
    good = FakeSource("good", "ok", [make_raw()])
    results = await asyncio.gather(
        run_source(FakeSource("bad", "crash"), rules, repo, NOW, 1, POLICY),
        run_source(good, rules, repo, NOW, 1, POLICY),
    )
    assert [r.status for r, _ in results] == ["error", "ok"]
    assert len(results[1][1]) == 1


# --- Circuit breaker ---------------------------------------------------------------------------


def test_breaker_opens_after_threshold_and_doubles_cooldown() -> None:
    h = SourceHealth(source="indeed")
    for _ in range(2):
        h = breaker.after(h, "blocked", NOW, POLICY, "HTTP 429")
        assert breaker.state(h, NOW, POLICY) == "closed"
    h = breaker.after(h, "blocked", NOW, POLICY, "HTTP 429")
    assert breaker.state(h, NOW, POLICY) == "open"
    assert h.open_until == NOW + timedelta(hours=6)
    assert h.last_error == "HTTP 429"

    later = NOW + timedelta(hours=7)
    assert breaker.state(h, later, POLICY) == "half_open"
    h = breaker.after(h, "timeout", later, POLICY)  # el intento semiabierto falla: se reabre el doble
    assert h.open_until == later + timedelta(hours=12)

    much_later = later + timedelta(hours=13)
    h = breaker.after(h, "ok", much_later, POLICY)
    assert breaker.state(h, much_later, POLICY) == "closed"
    assert h.consecutive_failures == 0 and h.times_opened == 0 and h.last_ok_at == much_later


def test_cooldown_is_capped() -> None:
    h = SourceHealth(source="indeed", consecutive_failures=3, times_opened=10)
    h = breaker.after(h, "error", NOW, POLICY)
    assert h.open_until == NOW + timedelta(hours=48)


def test_repeated_empty_linkedin_counts_as_silent_block() -> None:
    h = SourceHealth(source="linkedin")
    for _ in range(3):
        h = breaker.after(h, "empty", NOW, POLICY)
    assert h.consecutive_failures == 1 and "silencioso" in (h.last_error or "")
    other = SourceHealth(source="indeed")
    for _ in range(5):
        other = breaker.after(other, "empty", NOW, POLICY)
    assert other.consecutive_failures == 0


async def test_open_breaker_skips_the_source(repo: Repository, rules: GoldenRules) -> None:
    repo.save_source_health(
        SourceHealth(source="x", consecutive_failures=3, open_until=NOW + timedelta(hours=1))
    )
    source = FakeSource("x", "ok")
    run, _ = await run_source(source, rules, repo, NOW, 1, POLICY)
    assert run.status == "skipped_breaker_open"
    assert run.retry_at == NOW + timedelta(hours=1)
    assert source.calls == 0


async def test_failures_persist_and_open_the_breaker(repo: Repository, rules: GoldenRules) -> None:
    for _ in range(3):
        run, _ = await run_source(FakeSource("x", "blocked"), rules, repo, NOW, 1, POLICY)
    assert run.retry_at == NOW + timedelta(hours=6)
    assert breaker.is_open(repo.source_health("x"), NOW)


# --- jobspy ------------------------------------------------------------------------------------


def test_row_to_raw_maps_pandas_values() -> None:
    nan = float("nan")
    row = {
        "id": "li-4012345678",
        "site": "linkedin",
        "job_url": "https://www.linkedin.com/jobs/view/4012345678",
        "job_url_direct": nan,
        "title": "Junior AI Engineer",
        "company": "Acme",
        "location": "Málaga, Andalusia, Spain",
        "date_posted": date(2026, 10, 14),
        "is_remote": False,
        "description": "**Python**",
        "min_amount": nan,
        "max_amount": 30000.0,
        "currency": "EUR",
        "interval": "yearly",
    }
    raw = row_to_raw(row, "linkedin")
    assert raw["site_job_id"] == "li-4012345678"
    assert raw["salary_min"] is None and raw["salary_max"] == 30000.0
    assert raw["salary_interval"] == "yearly"
    assert raw["date_posted"] == date(2026, 10, 14)


class FakeFrame:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def to_dict(self, orient: str) -> list[dict]:
        return self.rows


def _scraper(rows: list[dict], log_error: str | None = None, site_logger: str = "JobSpy:LinkedIn"):
    calls: list[dict] = []

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        if log_error:
            logging.getLogger(site_logger).error(log_error)
        return FakeFrame(rows)

    scrape_jobs.calls = calls  # type: ignore[attr-defined]
    return scrape_jobs


async def test_jobspy_calls_one_site_per_query(rules: GoldenRules) -> None:
    row = {
        "id": "li-1",
        "job_url": "https://www.linkedin.com/jobs/view/1000001",
        "title": "Junior AI Engineer",
        "company": "Acme",
        "location": "Málaga",
        "description": "Python",
    }
    scraper = _scraper([row])
    source = JobspySource("linkedin", pause_s=(0, 0), scraper=scraper)
    result = await source.fetch(rules)
    assert len(scraper.calls) == 2  # las dos búsquedas de ejemplo incluyen LinkedIn
    assert all(call["site_name"] == ["linkedin"] for call in scraper.calls)
    assert scraper.calls[0]["fetch_description"] is True
    assert scraper.calls[0]["country_indeed"] == "spain"
    assert len(result.jobs) == 2 and result.invalid == 0


async def test_jobspy_logged_429_is_blocked(rules: GoldenRules) -> None:
    source = JobspySource(
        "linkedin", pause_s=(0, 0), scraper=_scraper([], "LinkedIn response status code 429")
    )
    with pytest.raises(SourceBlockedError) as exc:
        await source.fetch(rules)
    assert exc.value.code == "HTTP_429"


async def test_jobspy_other_logged_error_is_error(rules: GoldenRules) -> None:
    source = JobspySource(
        "indeed", pause_s=(0, 0), scraper=_scraper([], "Indeed: bad gateway", "JobSpy:Indeed")
    )
    with pytest.raises(SourceError) as exc:
        await source.fetch(rules)
    assert not isinstance(exc.value, SourceBlockedError)


async def test_jobspy_no_errors_and_no_rows_is_empty(rules: GoldenRules) -> None:
    result = await JobspySource("google", pause_s=(0, 0), scraper=_scraper([])).fetch(rules)
    assert result.jobs == [] and result.fetched == 0


# --- Feeds -------------------------------------------------------------------------------------


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@respx.mock
async def test_remotive_maps_scope_into_location(rules: GoldenRules) -> None:
    respx.get(RemotiveSource.url).mock(return_value=httpx.Response(200, content=_fixture("remotive.json")))
    async with httpx.AsyncClient() as client:
        result = await RemotiveSource(client).fetch(rules)
    assert result.fetched == 3 and result.invalid == 1  # la fila sin URL válida se descarta y se cuenta
    first, second = result.jobs
    assert first.location == "Remote (Europe)" and first.is_remote is True
    assert first.date_posted == date(2026, 10, 14)
    assert second.location == "Remote (USA Only)"


@respx.mock
async def test_arbeitnow_reads_remote_flag(rules: GoldenRules) -> None:
    respx.get(ArbeitnowSource.url).mock(return_value=httpx.Response(200, content=_fixture("arbeitnow.json")))
    async with httpx.AsyncClient() as client:
        result = await ArbeitnowSource(client).fetch(rules)
    assert [j.is_remote for j in result.jobs] == [True, False]
    assert result.jobs[0].site_job_id == "junior-python-developer-example-gmbh-123"


@respx.mock
async def test_rss_feed_extracts_company_from_title(rules: GoldenRules) -> None:
    feed = RssFeed(name="Ejemplo", url="https://empleo.example.com/rss")
    respx.get(feed.url).mock(return_value=httpx.Response(200, content=_fixture("feed.xml")))
    async with httpx.AsyncClient() as client:
        result = await RssSource(client, feed).fetch(rules)
    first, second = result.jobs
    assert (first.title, first.company) == ("Desarrollador Python Junior", "Ejemplo Tech")
    assert first.date_posted == date(2026, 10, 14)
    assert second.company == "Ejemplo"  # sin "en/at": nombre del feed


@pytest.mark.parametrize(
    ("status", "error"), [(429, SourceBlockedError), (403, SourceBlockedError), (500, SourceError)]
)
@respx.mock
async def test_feed_http_errors_are_classified(rules: GoldenRules, status: int, error: type) -> None:
    respx.get(RemotiveSource.url).mock(return_value=httpx.Response(status))
    async with httpx.AsyncClient() as client:
        with pytest.raises(error):
            await RemotiveSource(client).fetch(rules)


@respx.mock
async def test_feed_bad_json_is_an_error(rules: GoldenRules) -> None:
    respx.get(RemotiveSource.url).mock(return_value=httpx.Response(200, content=b"<html>"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="JSON"):
            await RemotiveSource(client).fetch(rules)


async def test_registry_builds_configured_sources(rules: GoldenRules) -> None:
    async with httpx.AsyncClient() as client:
        names = [s.name for s in build_sources(rules, client, (0, 0))]
    assert names == ["linkedin", "indeed", "google", "remotive", "arbeitnow"]
