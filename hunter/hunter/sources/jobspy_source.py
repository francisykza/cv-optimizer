"""LinkedIn, Indeed y Google Jobs vía `python-jobspy` (extra opcional `scrape`).

Una instancia por portal y una llamada a `scrape_jobs` por búsqueda (nunca todos los portales a la
vez): así un bloqueo de LinkedIn no afecta a Indeed. Desde jobspy 1.2 los portales no lanzan
excepciones al fallar, solo lo registran en su logger (`JobSpy:LinkedIn`...); por eso se capturan
esos registros para distinguir "bloqueado" de "sin resultados".
"""

import asyncio
import logging
import math
import random
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from hunter.rules.schema import GoldenRules, JobspySite, SearchQuery
from hunter.sources.base import FetchResult, JobSource, SourceBlockedError, SourceError, validate_rows

logger = logging.getLogger(__name__)

_LOGGER_NAMES: dict[str, str] = {
    "linkedin": "JobSpy:LinkedIn",
    "indeed": "JobSpy:Indeed",
    "google": "JobSpy:Google",
}
_BLOCKED = re.compile(r"status code (?:429|403|999)|blocked|captcha|too many requests|rate limit", re.I)
_INTERVALS = {"yearly", "monthly", "weekly", "daily", "hourly"}

Scraper = Callable[..., Any]  # firma de jobspy.scrape_jobs (devuelve un DataFrame)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage()[:300])


def _clean(value: Any) -> Any:
    """NaN/NaT de pandas -> None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if type(value).__name__ in ("NaTType", "NAType"):
        return None
    return value


def _as_date(value: Any) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def row_to_raw(row: dict[str, Any], site: str) -> dict[str, Any]:
    """Fila del DataFrame de jobspy -> dict compatible con RawJob."""
    r = {k: _clean(v) for k, v in row.items()}
    interval = (r.get("interval") or "").lower() or None
    return {
        "site": site,
        "site_job_id": str(r["id"]) if r.get("id") else None,
        "url": r.get("job_url_direct") if site == "google" and r.get("job_url_direct") else r.get("job_url"),
        "title": r.get("title") or "",
        "company": r.get("company") or "",
        "location": r.get("location") or "",
        "is_remote": bool(r["is_remote"]) if r.get("is_remote") is not None else None,
        "date_posted": _as_date(r.get("date_posted")),
        "description": r.get("description") or "",
        "salary_min": r.get("min_amount"),
        "salary_max": r.get("max_amount"),
        "salary_currency": r.get("currency"),
        "salary_interval": interval if interval in _INTERVALS else None,
    }


def _default_scraper() -> Scraper:
    try:
        from jobspy import scrape_jobs  # import perezoso: extra opcional y pesado
    except ImportError as exc:
        raise SourceError(
            'python-jobspy no está instalado: pip install -e ".[scrape]"', code="JOBSPY_MISSING"
        ) from exc
    return scrape_jobs


class JobspySource(JobSource):
    def __init__(
        self,
        site: JobspySite,
        pause_s: tuple[float, float] = (3.0, 8.0),
        scraper: Scraper | None = None,
    ) -> None:
        self.site = site
        self.name = site
        self._pause_s = pause_s
        self._scraper = scraper

    def queries(self, rules: GoldenRules) -> list[SearchQuery]:
        return [q for q in rules.search.queries if self.site in q.sites]

    async def fetch(self, rules: GoldenRules) -> FetchResult:
        scraper = self._scraper or _default_scraper()
        queries = self.queries(rules)
        result = FetchResult()
        problems: list[str] = []
        for i, query in enumerate(queries):
            if i:
                await asyncio.sleep(random.uniform(*self._pause_s))  # noqa: S311 (jitter, no cripto)
            rows, errors = await asyncio.to_thread(
                self._scrape_one, scraper, query, rules.search.country_indeed
            )
            partial = validate_rows((row_to_raw(row, self.site) for row in rows), self.site)
            result.jobs.extend(partial.jobs)
            result.fetched += partial.fetched
            result.invalid += partial.invalid
            if errors and not rows:
                problems.extend(errors)

        if problems and not result.jobs:
            message = "; ".join(dict.fromkeys(problems))[:500]
            if any(_BLOCKED.search(p) for p in problems):
                raise SourceBlockedError(message, code=_status_code(message) or "BLOCKED")
            raise SourceError(message, code="SCRAPER_ERROR")
        if problems:
            result.warning = f"{len(problems)} búsqueda(s) con errores: {problems[0]}"[:500]
        return result

    def _scrape_one(self, scraper: Scraper, query: SearchQuery, country: str) -> tuple[list[dict], list[str]]:
        capture = _Capture()
        jobspy_logger = logging.getLogger(_LOGGER_NAMES[self.site])
        jobspy_logger.addHandler(capture)
        try:
            frame = scraper(
                site_name=[self.site],
                search_term=query.term,
                google_search_term=query.google_term or f"{query.term} jobs near {query.location}",
                location=query.location,
                results_wanted=query.results_wanted,
                hours_old=query.hours_old,
                is_remote=bool(query.is_remote),
                country_indeed=country,
                fetch_description=True,
                description_format="markdown",
                verbose=0,
            )
        except Exception as exc:  # noqa: BLE001 — se clasifica como error de la fuente
            return [], [f"{type(exc).__name__}: {exc}"[:300]]
        finally:
            jobspy_logger.removeHandler(capture)
        rows = [] if frame is None or len(frame) == 0 else frame.to_dict("records")
        return rows, capture.messages


def _status_code(message: str) -> str | None:
    match = re.search(r"status code (\d{3})", message)
    return f"HTTP_{match.group(1)}" if match else None
