"""Orquestador del pipeline (SPEC §3.3): ingesta → normalización → dedup → guillotina → pre-score.

Idempotente y reanudable: cada oferta se confirma en su propia transacción, y repetir un run con los
mismos datos no crea ofertas nuevas (capa 1 de la deduplicación). El juez IA llega en la Fase 2: de
momento las ofertas que pasan la guillotina quedan en `pending_judge`.
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from hunter.models import NormalizedJob, RawJob, Run, RunMode, RunTrigger, SourceRun
from hunter.pipeline.dedup import NEW, DedupDecision, decide_by_content, decide_by_key, title_level
from hunter.pipeline.normalize import normalize
from hunter.pipeline.prescore import prescore
from hunter.rules.engine import JobFacts, guillotine
from hunter.rules.schema import GoldenRules
from hunter.sources.base import JobSource, run_source
from hunter.sources.breaker import BreakerPolicy
from hunter.store.repository import Repository, utcnow

logger = logging.getLogger(__name__)

# Un run sin latido durante este tiempo se considera huérfano (PC apagado, proceso matado).
STALE_RUN_AFTER = timedelta(minutes=2)
HEARTBEAT_EVERY_JOBS = 20

_FAILED_SOURCE = frozenset({"blocked", "timeout", "error"})


class RunInProgressError(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Ya hay una búsqueda en marcha ({run_id}).")
        self.run_id = run_id


@dataclass
class PipelineConfig:
    source_timeout_s: float = 90.0
    breaker: BreakerPolicy = field(default_factory=BreakerPolicy)
    dedup_window_days: int = 60
    profile_terms: list[str] = field(default_factory=list)


def run_status(sources: Sequence[SourceRun]) -> str:
    """ok: ninguna fuente falló · partial: alguna falló pero otra funcionó · failed: fallaron todas."""
    failed = [s for s in sources if s.status in _FAILED_SOURCE]
    if not failed:
        return "ok"
    if len(failed) == len(sources):
        return "failed"
    return "partial"


class Pipeline:
    def __init__(self, repo: Repository, rules: GoldenRules, config: PipelineConfig) -> None:
        self.repo = repo
        self.rules = rules
        self.config = config

    async def run(
        self,
        sources: Sequence[JobSource],
        trigger: RunTrigger = "cli",
        mode: RunMode = "ingest_only",
        now: datetime | None = None,
    ) -> Run:
        now = now or utcnow()
        orphans = self.repo.fail_orphan_runs(STALE_RUN_AFTER)
        if orphans:
            logger.warning("orphan_runs_failed count=%d", orphans)
        live = self.repo.live_run(STALE_RUN_AFTER)
        if live:
            raise RunInProgressError(live)

        run = Run(
            id=uuid.uuid4().hex,
            trigger=trigger,
            mode=mode,
            status="running",
            started_at=now,
            rules_version=self.rules.version,
        )
        self.repo.create_run(run)
        logger.info(
            "run_started id=%s mode=%s sources=%d rules=%s", run.id, mode, len(sources), run.rules_version
        )
        try:
            if mode in ("ingest_only", "full"):
                await self._ingest(run, sources, now)
            if mode in ("full", "judge_only"):
                logger.info("judge_skipped reason=fase_2 run=%s", run.id)
            run.status = run_status(run.sources) if run.sources else "ok"
        except Exception as exc:
            logger.exception("run_failed id=%s", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            run.finished_at = utcnow()
            self.repo.finish_run(run)
            logger.info("run_finished id=%s status=%s counts=%s", run.id, run.status, run.counts.model_dump())
        return run

    async def _ingest(self, run: Run, sources: Sequence[JobSource], now: datetime) -> None:
        results = await asyncio.gather(
            *(
                run_source(s, self.rules, self.repo, now, self.config.source_timeout_s, self.config.breaker)
                for s in sources
            )
        )
        for source_run, raws in results:
            run.sources.append(source_run)
            self.repo.save_source_run(run.id, source_run)
            run.counts.fetched += len(raws)
            for i, raw in enumerate(raws, 1):
                self.process(raw, run, now)
                if i % HEARTBEAT_EVERY_JOBS == 0:
                    self.repo.heartbeat(run.id, run.counts)
            self.repo.heartbeat(run.id, run.counts)

    def process(self, raw: RawJob, run: Run, now: datetime) -> str:
        """Procesa una oferta en su propia transacción.

        Devuelve 'duplicate', 'discarded' o 'pending_judge'."""
        job = normalize(raw)
        with self.repo.transaction():
            decision = self._dedup(job, now)
            if decision.duplicate:
                if decision.job_id:
                    self.repo.add_alias(decision.job_id, job, now)
                    self.repo.touch_job(decision.job_id, now)
                run.counts.duplicates += 1
                return "duplicate"

            facts = JobFacts.from_normalized(job)
            today = now.date()
            result = guillotine(facts, self.rules, today)
            stage = "pending_judge" if result.passed else "discarded"
            score = prescore(facts, self.rules, self.config.profile_terms, today) if result.passed else 0
            job_id = self.repo.insert_job(job, stage, score, now)
            self.repo.save_guillotine(job_id, result, now)
        run.counts.new += 1
        if result.passed:
            run.counts.pending_judge += 1
        else:
            run.counts.discarded += 1
        return stage

    def _dedup(self, job: NormalizedJob, now: datetime) -> DedupDecision:
        raw = job.raw
        job_id = self.repo.find_by_source(job.url_canonical, raw.site, raw.site_job_id)
        if job_id:
            return DedupDecision(True, "source", job_id)
        if self.repo.purged_url_seen(job.url_canonical):
            return DedupDecision(True, "fingerprint", None)
        since = now - timedelta(days=self.config.dedup_window_days)
        decision = decide_by_key(job.simhash, self.repo.candidates_by_key(job.job_key, since))
        if decision.duplicate:
            return decision
        recent = self.repo.recent_simhashes(since)
        decision = decide_by_content(job.simhash, recent, title_level(job.title_norm))
        return decision if decision.duplicate else NEW

    def reevaluate(self, window_days: int, today: date | None = None) -> tuple[int, int, int]:
        """Vuelve a pasar la guillotina (0 tokens) a las ofertas recientes `discarded` y `pending_judge`
        tras cambiar las reglas. Devuelve (evaluadas, ahora pendientes, ahora descartadas)."""
        now = utcnow()
        today = today or now.date()
        jobs = self.repo.jobs_seen_since(now - timedelta(days=window_days), ("discarded", "pending_judge"))
        to_pending = to_discarded = 0
        for job in jobs:
            result = guillotine(job.facts, self.rules, today)
            with self.repo.transaction():
                self.repo.save_guillotine(job.id, result, now)
                if result.passed and job.stage == "discarded":
                    score = prescore(job.facts, self.rules, self.config.profile_terms, today)
                    self.repo.set_stage(job.id, "pending_judge", score)
                    to_pending += 1
                elif not result.passed and job.stage == "pending_judge":
                    self.repo.set_stage(job.id, "discarded", 0)
                    to_discarded += 1
        return len(jobs), to_pending, to_discarded
