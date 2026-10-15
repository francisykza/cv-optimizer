"""Interfaz común de las fuentes y ejecución aislada (SPEC §6.1 y §9).

Cada fuente corre en su propia tarea con timeout: si un portal bloquea o se cuelga, el resto sigue.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from hunter.models import RawJob, SourceRun
from hunter.rules.schema import GoldenRules
from hunter.sources import breaker
from hunter.store.repository import Repository, SourceHealth

logger = logging.getLogger(__name__)


class SourceError(Exception):
    status = "error"

    def __init__(self, message: str, code: str = "SOURCE_ERROR") -> None:
        super().__init__(message)
        self.code = code


class SourceBlockedError(SourceError):
    """El portal rechaza las peticiones (429, 403, 999 de LinkedIn, captcha...)."""

    status = "blocked"


@dataclass
class FetchResult:
    jobs: list[RawJob] = field(default_factory=list)
    fetched: int = 0
    invalid: int = 0
    warning: str | None = None  # p. ej. una de varias búsquedas falló


class JobSource(ABC):
    name: str

    @abstractmethod
    async def fetch(self, rules: GoldenRules) -> FetchResult:
        """Devuelve ofertas validadas o lanza SourceError/SourceBlockedError."""


def validate_rows(rows: Iterable[dict], source: str) -> FetchResult:
    """Valida fila a fila: una fila corrupta se cuenta y se registra, no tumba la fuente."""
    result = FetchResult()
    for row in rows:
        result.fetched += 1
        try:
            result.jobs.append(RawJob.model_validate(row))
        except ValidationError as exc:
            result.invalid += 1
            fields = ",".join(str(e["loc"][0]) for e in exc.errors() if e.get("loc"))
            logger.info("source_row_invalid source=%s fields=%s", source, fields)
    return result


async def run_source(
    source: JobSource,
    rules: GoldenRules,
    repo: Repository,
    now: datetime,
    timeout_s: float,
    policy: breaker.BreakerPolicy,
) -> tuple[SourceRun, list[RawJob]]:
    """Ejecuta una fuente con timeout y circuit breaker. Nunca lanza."""
    health = repo.source_health(source.name)
    if breaker.is_open(health, now):
        return (
            SourceRun(
                source=source.name,
                status="skipped_breaker_open",
                retry_at=health.open_until,
                error_code="BREAKER_OPEN",
                error_message=health.last_error,
            ),
            [],
        )

    started = time.monotonic()
    jobs: list[RawJob] = []
    try:
        result = await asyncio.wait_for(source.fetch(rules), timeout=timeout_s)
    except TimeoutError:
        run = SourceRun(
            source=source.name,
            status="timeout",
            error_code="TIMEOUT",
            error_message=f"Sin respuesta en {timeout_s:.0f} s",
        )
    except SourceError as exc:
        run = SourceRun(
            source=source.name, status=exc.status, error_code=exc.code, error_message=str(exc)[:500]
        )
    except Exception as exc:  # noqa: BLE001 — aislamiento: una fuente rota no tumba el run
        logger.exception("source_unexpected_error source=%s", source.name)
        run = SourceRun(
            source=source.name, status="error", error_code=type(exc).__name__, error_message=str(exc)[:500]
        )
    else:
        jobs = result.jobs
        run = SourceRun(
            source=source.name,
            status="ok" if jobs else "empty",
            fetched=result.fetched,
            valid=len(jobs),
            invalid=result.invalid,
            error_message=result.warning,
        )
    run.duration_ms = int((time.monotonic() - started) * 1000)

    new_health: SourceHealth = breaker.after(
        health, run.status, now, policy, run.error_message or run.error_code
    )
    repo.save_source_health(new_health)
    if breaker.is_open(new_health, now):
        run.retry_at = new_health.open_until
    logger.info(
        "source_done source=%s status=%s fetched=%d valid=%d invalid=%d ms=%d code=%s",
        run.source,
        run.status,
        run.fetched,
        run.valid,
        run.invalid,
        run.duration_ms,
        run.error_code,
    )
    return run, jobs
