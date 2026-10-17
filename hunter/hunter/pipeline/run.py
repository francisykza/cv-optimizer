"""Orquestador del pipeline (SPEC §3.3): ingesta → normalización → dedup → guillotina → pre-score
→ juez IA.

Idempotente y reanudable: cada oferta se confirma en su propia transacción, repetir un run con los
mismos datos no crea ofertas nuevas (capa 1 de la deduplicación) ni gasta tokens (caché de
veredictos), y lo que el juez no llega a evaluar (cuota o presupuesto) sigue en `pending_judge`
para la siguiente ejecución.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pydantic import ValidationError

from hunter.judge.judge import Judge, JudgeOutcome, JudgeStoppedError
from hunter.judge.limiter import QuotaExhaustedError
from hunter.judge.schema import JobVerdict, rank_score
from hunter.models import AppStatus, NormalizedJob, RawJob, Run, RunMode, RunTrigger, SourceRun, Stage
from hunter.pipeline.dedup import NEW, DedupDecision, decide_by_content, decide_by_key, title_level
from hunter.pipeline.normalize import normalize
from hunter.pipeline.prescore import prescore
from hunter.rules.engine import JobFacts, guillotine
from hunter.rules.schema import GoldenRules
from hunter.sources.base import JobSource, run_source
from hunter.sources.breaker import BreakerPolicy
from hunter.store.repository import Repository, StoredJob, utcnow

logger = logging.getLogger(__name__)

# Un run sin latido durante este tiempo se considera huérfano (PC apagado, proceso matado). Entre
# dos latidos del juez caben una espera del limitador (≤ 60 s) y una llamada con reintentos.
STALE_RUN_AFTER = timedelta(minutes=10)
HEARTBEAT_EVERY_JOBS = 20
# Errores transitorios seguidos del juez (timeouts, 5xx) tras los que se deja para otro run.
MAX_CONSECUTIVE_JUDGE_ERRORS = 3
# "Volver a juzgar con tu perfil" (SPEC §19.3) mira la última semana, como la re-evaluación de reglas,
# y no gasta tokens en lo que ya no se va a mirar: "No me interesa" y las ofertas ya inscritas.
REJUDGE_DAYS = 7
REJUDGE_APP_STATUSES: frozenset[AppStatus] = frozenset({"none", "saved", "sent_to_optimizer"})

_FAILED_SOURCE = frozenset({"blocked", "timeout", "error"})
_JUDGE_STOP_MESSAGES = {
    "rate_limit": "Cuota de Groq agotada: el resto de ofertas se juzgará en la siguiente ejecución.",
    "daily_budget": "Presupuesto diario de tokens agotado (HUNTER_DAILY_TOKEN_BUDGET).",
    "invalid_key": "Groq rechaza la clave: revisa GROQ_API_KEY en hunter/.env.",
}
# Al volver a juzgar con el perfil nuevo, lo que falta no vuelve a la cola: conserva su nota anterior.
_REJUDGE_STOP_MESSAGES = {
    **_JUDGE_STOP_MESSAGES,
    "rate_limit": (
        "Cuota de Groq agotada: las que faltan conservan su nota anterior. Vuelve a juzgarlas más tarde."
    ),
    "daily_budget": "Presupuesto diario de tokens agotado: las que faltan conservan su nota anterior.",
}


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


def outdated_jobs(repo: Repository, since: datetime, key_of: Callable[[StoredJob], str]) -> list[StoredJob]:
    """Ofertas juzgadas desde `since` cuya nota no es del perfil actual: `key_of` da la clave que tendría
    hoy su veredicto y no coincide con la guardada. Las mejor colocadas primero: si se acaba la cuota a
    mitad, lo que más se mira ya está al día."""
    jobs = [
        job
        for job in repo.jobs_seen_since(since, ("judged",))
        if job.app_status in REJUDGE_APP_STATUSES and job.verdict_key != key_of(job)
    ]
    return sorted(jobs, key=lambda job: job.rank_score or 0, reverse=True)


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
        judge: Judge | None = None,
        judge_limit: int | None = None,
        run_id: str | None = None,
    ) -> Run:
        now = now or utcnow()
        orphans = self.repo.fail_orphan_runs(STALE_RUN_AFTER)
        if orphans:
            logger.warning("orphan_runs_failed count=%d", orphans)
        live = self.repo.live_run(STALE_RUN_AFTER)
        if live:
            raise RunInProgressError(live)

        run = Run(
            id=run_id or uuid.uuid4().hex,
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
            if mode in ("full", "judge_only", "rejudge"):
                if judge is None:
                    run.error = "Sin GROQ_API_KEY: el juez no se ha ejecutado."
                    logger.warning("judge_skipped reason=no_key run=%s", run.id)
                elif mode == "rejudge":
                    await self.rejudge_outdated(run, judge, now, judge_limit)
                else:
                    await self.judge_pending(run, judge, now, judge_limit)
            # "Pendientes" es la cola total del juez al terminar, no solo lo nuevo de este run.
            run.counts.pending_judge = self.repo.count_by_stage().get("pending_judge", 0)
            run.status = run_status(run.sources) if run.sources else "ok"
            if run.status == "ok" and (run.budget_exhausted or run.error):
                run.status = "partial"
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

    async def judge_pending(self, run: Run, judge: Judge, now: datetime, limit: int | None = None) -> None:
        """Juzga la cola `pending_judge` (mejor pre-score primero) hasta acabarla, agotar la cuota o
        el presupuesto, o encadenar demasiados errores transitorios."""
        since = now - timedelta(days=self.config.dedup_window_days)
        queue = self.repo.jobs_by_stage("pending_judge", since)
        if limit is not None:
            queue = queue[:limit]
        logger.info("judge_started run=%s pending=%d", run.id, len(queue))
        await self._judge_queue(run, judge, queue)

    async def rejudge_outdated(self, run: Run, judge: Judge, now: datetime, limit: int | None = None) -> None:
        """Vuelve a juzgar las ofertas de la última semana cuya nota es de un perfil anterior (SPEC §19.3).
        Cada una conserva su nota hasta que llega la nueva; si el juez no puede leerla, se queda como
        estaba (y sigue contando como desactualizada)."""
        queue = outdated_jobs(self.repo, now - timedelta(days=REJUDGE_DAYS), judge.cache_key)
        if limit is not None:
            queue = queue[:limit]
        logger.info("rejudge_started run=%s outdated=%d", run.id, len(queue))
        await self._judge_queue(run, judge, queue, rejudge=True)

    async def _judge_queue(
        self, run: Run, judge: Judge, queue: list[StoredJob], rejudge: bool = False
    ) -> None:
        messages = _REJUDGE_STOP_MESSAGES if rejudge else _JUDGE_STOP_MESSAGES
        run.counts.judge_queue = len(queue)
        self.repo.heartbeat(run.id, run.counts)  # la vista muestra "0 de N" desde el primer momento
        errors_in_a_row = 0
        for job in queue:
            try:
                outcome = await judge.judge(job)
            except (JudgeStoppedError, QuotaExhaustedError) as exc:
                reason = getattr(exc, "reason", str(exc))
                run.budget_exhausted = reason in ("rate_limit", "daily_budget")
                run.error = messages.get(reason, str(exc))[:500]
                logger.warning("judge_stopped run=%s reason=%s", run.id, reason)
                break
            run.tokens_used += outcome.tokens
            if outcome.status == "error":
                errors_in_a_row += 1
                if errors_in_a_row >= MAX_CONSECUTIVE_JUDGE_ERRORS:
                    run.error = f"El juez falló {errors_in_a_row} veces seguidas ({outcome.error})."
                    break
                continue
            errors_in_a_row = 0
            self.save_outcome(job, outcome, judge, keep_verdict=rejudge)
            if outcome.status == "judge_failed":
                run.counts.judge_failed += 1
            else:
                run.counts.judged += 1
                run.counts.cache_hits += outcome.status == "cache_hit"
            self.repo.heartbeat(run.id, run.counts)

    def save_outcome(
        self, job: StoredJob, outcome: JudgeOutcome, judge: Judge, keep_verdict: bool = False
    ) -> None:
        """`keep_verdict`: al volver a juzgar con el perfil nuevo, un fallo no le quita a la oferta la
        nota que ya tenía."""
        with self.repo.transaction():
            if outcome.status != "cache_hit":
                self.repo.save_verdict(job.id, judge.record(outcome))
            if outcome.verdict is not None:
                rank = rank_score(outcome.verdict.match_score, job.prescore)
                self.repo.set_judged(job.id, "judged", outcome.cache_key, rank)
            elif not (keep_verdict and job.stage == "judged"):
                self.repo.set_judged(job.id, "judge_failed", outcome.cache_key, None, outcome.error)

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
        """Vuelve a pasar la guillotina (0 tokens) a las ofertas recientes tras cambiar las reglas.
        Las que ya tenían veredicto y ahora no pasan se descartan (conservan el veredicto en caché: si
        vuelven a pasar, el juez no gasta tokens).

        Devuelve (evaluadas, ahora pendientes, ahora descartadas)."""
        now = utcnow()
        today = today or now.date()
        stages: tuple[Stage, ...] = ("discarded", "pending_judge", "judged", "judge_failed")
        jobs = self.repo.jobs_seen_since(now - timedelta(days=window_days), stages)
        to_pending = to_discarded = 0
        for job in jobs:
            result = guillotine(job.facts, self.rules, today)
            with self.repo.transaction():
                self.repo.save_guillotine(job.id, result, now)
                if result.passed and job.stage == "discarded":
                    score = prescore(job.facts, self.rules, self.config.profile_terms, today)
                    self.repo.set_stage(job.id, "pending_judge", score)
                    to_pending += 1
                elif not result.passed and job.stage != "discarded":
                    self.repo.set_stage(job.id, "discarded", 0)
                    to_discarded += 1
        return len(jobs), to_pending, to_discarded

    def rescore(self) -> int:
        """Recalcula el pre-score con los términos del perfil actual (0 tokens) en las ofertas que siguen
        en juego: ordena la cola del juez, desempata el ranking y el juez lo ve en sus señales. Se calcula
        a la fecha en que llegó cada oferta, así solo cambia lo que depende del perfil.

        Devuelve cuántas han cambiado."""
        since = utcnow() - timedelta(days=self.config.dedup_window_days)
        changed = 0
        for job in self.repo.jobs_seen_since(since, ("pending_judge", "judged", "judge_failed")):
            score = prescore(job.facts, self.rules, self.config.profile_terms, job.first_seen.date())
            if score == job.prescore:
                continue
            match = self._match_score(job.verdict_key) if job.stage == "judged" else None
            with self.repo.transaction():
                self.repo.set_prescore(job.id, score, rank_score(match, score) if match is not None else None)
            changed += 1
        return changed

    def restore_cached(self, key_of: Callable[[StoredJob], str]) -> int:
        """Ofertas con nota de otro perfil que ya se juzgaron con el actual (has vuelto a un perfil
        anterior): recuperan esa nota de la caché sin gastar tokens. Devuelve cuántas."""
        since = utcnow() - timedelta(days=self.config.dedup_window_days)
        restored = 0
        for job in outdated_jobs(self.repo, since, key_of):
            key = key_of(job)
            match = self._match_score(key)
            if match is None:
                continue
            with self.repo.transaction():
                self.repo.set_judged(job.id, "judged", key, rank_score(match, job.prescore))
            restored += 1
        return restored

    def _match_score(self, verdict_key: str | None) -> int | None:
        """Nota del veredicto válido guardado con esa clave, o None."""
        stored = self.repo.cached_verdict(verdict_key) if verdict_key else None
        if stored is None or stored.status != "ok" or not stored.verdict_json:
            return None
        try:
            return JobVerdict.model_validate_json(stored.verdict_json).match_score
        except ValidationError:
            return None
