"""Montaje de las piezas (repositorio, pipeline, juez, fuentes) compartido por la CLI y la API local.

Así `python -m hunter run` (Programador de tareas) y `POST /api/v1/runs` (vista Buscador) ejecutan
exactamente el mismo código.
"""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
from app.services.llm.groq import GroqProvider

from hunter.config import Settings
from hunter.judge.judge import Judge, JudgeConfig, JudgeContext, model_family, verdict_key
from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard
from hunter.models import Run, RunMode, RunTrigger
from hunter.pipeline.prescore import load_profile_terms
from hunter.pipeline.run import Pipeline, PipelineConfig
from hunter.rules.schema import GoldenRules
from hunter.sources import breaker
from hunter.sources.registry import build_sources
from hunter.store.db import connect
from hunter.store.repository import Repository, StoredJob, utcnow


class ProfileMissingError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"No encuentro el perfil {path}. Ejecuta `python -m hunter init` y complétalo.")
        self.path = path


def open_repo(settings: Settings) -> Repository:
    return Repository(connect(settings.db_path))


def profile_path(rules: GoldenRules, settings: Settings) -> Path:
    """El perfil vive en la carpeta de datos. Las reglas anteriores a la SPEC 0.4.0 lo llaman
    `data/profile.md` (la carpeta de datos estaba dentro de `hunter/`): equivale a `profile.md`."""
    path = Path(rules.judge.profile_file)
    if path.is_absolute():
        return path
    if path.parts[:1] == ("data",):
        path = Path(*path.parts[1:]) if len(path.parts) > 1 else Path("profile.md")
    return settings.data_dir / path


def breaker_policy(settings: Settings) -> breaker.BreakerPolicy:
    return breaker.BreakerPolicy(
        settings.hunter_breaker_threshold,
        settings.hunter_breaker_cooldown_h,
        settings.hunter_breaker_max_cooldown_h,
    )


def build_pipeline(repo: Repository, rules: GoldenRules, settings: Settings) -> Pipeline:
    return Pipeline(
        repo,
        rules,
        PipelineConfig(
            source_timeout_s=settings.hunter_source_timeout_s,
            breaker=breaker_policy(settings),
            dedup_window_days=settings.hunter_dedup_window_days,
            profile_terms=load_profile_terms(profile_path(rules, settings)),
        ),
    )


def current_verdict_key(
    rules: GoldenRules, settings: Settings, profile_text: str
) -> Callable[[StoredJob], str]:
    """La clave que tendría hoy el veredicto de cada oferta, con este perfil, las prioridades de las
    reglas, el prompt y la familia de modelo actuales (la misma que calcula el juez)."""
    context_hash = JudgeContext.from_rules(rules, profile_text).hash
    family = model_family(settings.groq_model_primary)
    return lambda job: verdict_key(job.desc_sha256, context_hash, family)


def llm_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def build_judge(
    repo: Repository, rules: GoldenRules, settings: Settings, client: httpx.AsyncClient
) -> Judge | None:
    """None si no hay GROQ_API_KEY. Lanza ProfileMissingError si falta el perfil."""
    key = settings.server_api_key
    if key is None:
        return None
    provider = GroqProvider(
        client=client,
        api_key=key,
        models=settings.groq_models,
        # "byok": es la clave del propio usuario; un 401 se informa como clave no válida.
        mode="byok",
        base_url=settings.groq_base_url,
        timeout_s=settings.hunter_judge_timeout_s,
        reasoning_effort=settings.hunter_reasoning_effort,
    )
    path = profile_path(rules, settings)
    try:
        profile_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileMissingError(path) from exc
    return Judge(
        provider,
        repo,
        AdaptiveLimiter(tokens_per_minute=settings.hunter_tokens_per_minute),
        BudgetGuard(repo, settings.hunter_daily_token_budget),
        JudgeContext.from_rules(rules, profile_text),
        JudgeConfig(
            model=settings.groq_model_primary,
            max_input_chars=settings.hunter_judge_max_input_chars,
            max_output_tokens=settings.hunter_judge_max_output_tokens,
        ),
    )


async def execute_run(
    repo: Repository,
    rules: GoldenRules,
    settings: Settings,
    *,
    mode: RunMode = "full",
    trigger: RunTrigger = "cli",
    only: list[str] | None = None,
    judge_limit: int | None = None,
    run_id: str | None = None,
) -> Run:
    """Un run: fuentes y guillotina (full e ingest_only) y juez (salvo ingest_only; en rejudge, solo
    las notas de un perfil anterior). Lanza RunInProgressError si ya hay otro en marcha."""
    pipeline = build_pipeline(repo, rules, settings)
    async with llm_client() as client:
        portals = mode in ("full", "ingest_only")
        sources = build_sources(rules, client, settings.hunter_source_pause_s) if portals else []
        if only:
            sources = [s for s in sources if s.name in only]
        judge = build_judge(repo, rules, settings, client) if mode != "ingest_only" else None
        run = await pipeline.run(
            sources, trigger=trigger, mode=mode, judge=judge, judge_limit=judge_limit, run_id=run_id
        )
    if settings.hunter_retention_days > 0:
        purge(repo, settings)
    return run


def purge(repo: Repository, settings: Settings) -> int:
    now = utcnow()
    days = settings.hunter_retention_days
    return repo.purge(now - timedelta(days=days), now - timedelta(days=days * 2))
