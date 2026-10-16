"""API local del Job Hunter (SPEC §8): `python -m hunter serve` → http://127.0.0.1:8001.

- Solo escucha en 127.0.0.1 y exige la cabecera `X-Hunter-Token` (salvo /health). Al ser una cabecera
  propia, el navegador hace preflight CORS: una web cualquiera no puede lanzar búsquedas ni leer datos.
- Los runs se lanzan en segundo plano dentro del mismo proceso y se consultan con GET /runs/{id}.
- Reutiliza el formato de errores, el request_id y el logging del backend del Optimizador.
"""

import asyncio
import logging
import secrets
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

import httpx
from app.api.errors import register_exception_handlers
from app.core.exceptions import AppError
from app.core.middleware import RequestContextMiddleware
from app.services.job_url_extractor import extract_job_offer
from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from hunter import __version__, services
from hunter.api import views
from hunter.api.schemas import (
    AppStatusUpdate,
    Handoff,
    HealthResponse,
    JobDetail,
    JobItem,
    JobsPage,
    JobsView,
    LastRun,
    RulesResponse,
    RulesSaved,
    RulesVersion,
    RunAccepted,
    RunRequest,
    RunsResponse,
    SimulateRequest,
    SimulateResponse,
    SourceHealthOut,
)
from hunter.config import Settings, get_settings
from hunter.judge.judge import JudgeStoppedError
from hunter.judge.limiter import QuotaExhaustedError
from hunter.models import AppStatus, Run
from hunter.pipeline.run import STALE_RUN_AFTER, RunInProgressError
from hunter.pipeline.simulate import simulate
from hunter.rules.schema import GoldenRules
from hunter.sources import breaker
from hunter.store.repository import Repository, StoredJob, utcnow

logger = logging.getLogger(__name__)
LIST_DAYS_DEFAULT = 14
REEVALUATE_DAYS = 7


# --- Errores -----------------------------------------------------------------------------------


class TokenMissingError(AppError):
    status_code = 503
    code = "HUNTER_TOKEN_MISSING"
    message = "La API local no tiene token. Ejecuta `python -m hunter init`."


class TokenInvalidError(AppError):
    status_code = 401
    code = "HUNTER_TOKEN_INVALID"
    message = "Falta el token local o no coincide (cabecera X-Hunter-Token)."


class NoRulesError(AppError):
    status_code = 409
    code = "NO_RULES"
    message = "No hay Reglas de Oro activas. Ejecuta `python -m hunter init`."


class JobNotFoundError(AppError):
    status_code = 404
    code = "JOB_NOT_FOUND"
    message = "No existe esa oferta."


class RunNotFoundError(AppError):
    status_code = 404
    code = "RUN_NOT_FOUND"
    message = "No existe esa ejecución."


class RunBusyError(AppError):
    status_code = 409
    code = "RUN_IN_PROGRESS"
    message = "Ya hay una búsqueda en marcha."


class GroqKeyMissingError(AppError):
    status_code = 503
    code = "GROQ_KEY_MISSING"
    message = "Falta GROQ_API_KEY en hunter/.env para usar el juez IA."


class JudgeBudgetError(AppError):
    status_code = 429
    code = "JUDGE_BUDGET_EXHAUSTED"
    message = "Sin cuota de Groq o sin presupuesto de tokens hoy. Inténtalo más tarde."


class JudgeUnavailableError(AppError):
    status_code = 502
    code = "JUDGE_ERROR"
    message = "El juez IA no ha podido responder. Inténtalo de nuevo."


class RulesInvalidError(AppError):
    status_code = 422
    code = "RULES_INVALID"
    message = "Las reglas no son válidas."

    def __init__(self, details: list[dict[str, str]]) -> None:
        self.details = details
        super().__init__()


async def _rules_invalid(request: Request, exc: RulesInvalidError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
                "details": exc.details,
            }
        },
    )


# --- Dependencias ------------------------------------------------------------------------------


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_repo(settings: SettingsDep) -> Iterator[Repository]:
    repo = services.open_repo(settings)
    try:
        yield repo
    finally:
        repo.conn.close()


RepoDep = Annotated[Repository, Depends(get_repo)]


def require_token(settings: SettingsDep, x_hunter_token: Annotated[str | None, Header()] = None) -> None:
    expected = settings.hunter_token.get_secret_value() if settings.hunter_token else ""
    if not expected:
        raise TokenMissingError()
    if not x_hunter_token or not secrets.compare_digest(x_hunter_token.encode(), expected.encode()):
        raise TokenInvalidError()


def active_rules(repo: Repository) -> GoldenRules:
    rules = repo.active_rules()
    if rules is None:
        raise NoRulesError()
    return rules


def find_job(repo: Repository, job_id: str) -> StoredJob:
    job = repo.get_job(job_id)
    if job is None or job.id != job_id:  # en la API los ids van completos
        raise JobNotFoundError()
    return job


def parse_rules(payload: object) -> GoldenRules:
    try:
        return GoldenRules.model_validate(payload)
    except ValidationError as exc:
        details = [{"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
        raise RulesInvalidError(details) from exc


# --- Rutas -------------------------------------------------------------------------------------

public = APIRouter()
api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])


@public.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    last_run = None
    db_ok = True
    try:
        repo = services.open_repo(settings)
        try:
            runs = repo.recent_runs(1)
            if runs:
                last_run = LastRun(id=runs[0].id, status=runs[0].status, finished_at=runs[0].finished_at)
        finally:
            repo.conn.close()
    except Exception:  # noqa: BLE001 — /health nunca falla: informa
        logger.exception("health_db_error")
        db_ok = False
    return HealthResponse(
        version=__version__,
        db_ok=db_ok,
        groq_key_configured=settings.server_api_key is not None,
        token_configured=bool(settings.hunter_token and settings.hunter_token.get_secret_value()),
        last_run=last_run,
    )


@api.get("/rules", response_model=RulesResponse)
def get_rules(repo: RepoDep) -> RulesResponse:
    rules = active_rules(repo)
    history = [RulesVersion(version=v, created_at=c, active=a) for v, c, a in repo.rules_history()]
    return RulesResponse(version=rules.version, rules=rules, history=history)


@api.put("/rules", response_model=RulesSaved)
def put_rules(payload: dict, repo: RepoDep, settings: SettingsDep) -> RulesSaved:
    rules = parse_rules(payload.get("rules"))
    version = repo.save_rules(rules)
    total, to_pending, to_discarded = services.build_pipeline(repo, rules, settings).reevaluate(
        REEVALUATE_DAYS
    )
    return RulesSaved(
        version=version, reevaluated=total, now_pending_judge=to_pending, now_discarded=to_discarded
    )


@api.post("/rules/simulate", response_model=SimulateResponse)
def simulate_rules(payload: dict, repo: RepoDep) -> SimulateResponse:
    proposed = parse_rules(payload.get("rules"))
    request = SimulateRequest(rules=proposed, window_days=payload.get("window_days", 7))
    return simulate(repo, active_rules(repo), request.rules, window_days=request.window_days)


@api.post("/runs", response_model=RunAccepted, status_code=202)
async def start_run(body: RunRequest, request: Request, repo: RepoDep, settings: SettingsDep) -> RunAccepted:
    state = request.app.state
    rules = active_rules(repo)
    task: asyncio.Task | None = state.run_task
    if (task is not None and not task.done()) or repo.live_run(STALE_RUN_AFTER):
        raise RunBusyError()
    if body.mode == "judge_only" and settings.server_api_key is None:
        raise GroqKeyMissingError()
    if body.retry_failed:
        repo.reset_failed()

    run_id = uuid.uuid4().hex

    async def background() -> None:
        run_repo = services.open_repo(settings)
        try:
            await services.execute_run(
                run_repo,
                rules,
                settings,
                mode=body.mode,
                trigger="api",
                only=body.only,
                judge_limit=body.judge_limit,
                run_id=run_id,
            )
        except RunInProgressError:
            logger.warning("api_run_collision run=%s", run_id)
        except Exception:
            logger.exception("api_run_failed run=%s", run_id)
        finally:
            run_repo.conn.close()

    state.run_task = asyncio.create_task(background())
    state.run_pending = Run(
        id=run_id,
        trigger="api",
        mode=body.mode,
        status="running",
        started_at=utcnow(),
        rules_version=rules.version,
    )
    return RunAccepted(run_id=run_id)


@api.get("/runs", response_model=RunsResponse)
def list_runs(repo: RepoDep, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> RunsResponse:
    return RunsResponse(items=repo.recent_runs(limit))


@api.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: str, request: Request, repo: RepoDep) -> Run:
    run = repo.get_run(run_id)
    if run is not None:
        return run
    pending: Run | None = request.app.state.run_pending
    task: asyncio.Task | None = request.app.state.run_task
    if pending is not None and pending.id == run_id and task is not None and not task.done():
        return pending  # el run aún no ha escrito su fila
    raise RunNotFoundError()


@api.get("/sources", response_model=list[SourceHealthOut])
def list_sources(repo: RepoDep, settings: SettingsDep) -> list[SourceHealthOut]:
    policy = services.breaker_policy(settings)
    now = utcnow()
    return [
        SourceHealthOut(
            source=h.source,
            state=breaker.state(h, now, policy),
            consecutive_failures=h.consecutive_failures,
            open_until=h.open_until,
            last_ok_at=h.last_ok_at,
            last_error=h.last_error,
        )
        for h in repo.all_source_health()
    ]


@api.get("/jobs", response_model=JobsPage)
def list_jobs(
    repo: RepoDep,
    view: JobsView = "ranked",
    app_status: AppStatus | None = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    days: Annotated[int, Query(ge=1, le=365)] = LIST_DAYS_DEFAULT,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: str | None = None,
) -> JobsPage:
    now = utcnow()
    if view == "ranked" and min_score is None:
        min_score = active_rules(repo).judge.min_score_to_show
    jobs = repo.jobs_seen_since(now - timedelta(days=days), views.VIEW_STAGES[view])
    selected = views.select_jobs(repo, jobs, view, app_status=app_status, min_score=min_score, q=q)
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    page = selected[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(selected) else None
    return JobsPage(
        items=[views.to_item(repo, job, now, verdict) for job, verdict in page],
        total=len(selected),
        next_cursor=next_cursor,
    )


@api.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str, repo: RepoDep) -> JobDetail:
    return views.to_detail(repo, find_job(repo, job_id), utcnow())


@api.patch("/jobs/{job_id}", response_model=JobItem)
def update_job(job_id: str, body: AppStatusUpdate, repo: RepoDep) -> JobItem:
    job = find_job(repo, job_id)
    repo.set_app_status(job.id, body.app_status)
    return views.to_item(repo, find_job(repo, job_id), utcnow())


@api.post("/jobs/{job_id}/rejudge", response_model=JobItem)
async def rejudge(job_id: str, repo: RepoDep, settings: SettingsDep) -> JobItem:
    job = find_job(repo, job_id)
    rules = active_rules(repo)
    if settings.server_api_key is None:
        raise GroqKeyMissingError()
    async with services.llm_client() as client:
        try:
            judge = services.build_judge(repo, rules, settings, client)
        except services.ProfileMissingError as exc:
            raise JudgeUnavailableError(str(exc)) from exc
        if judge is None:
            raise GroqKeyMissingError()
        try:
            outcome = await judge.judge(job, force=True)
        except (JudgeStoppedError, QuotaExhaustedError) as exc:
            raise JudgeBudgetError() from exc
    if outcome.status == "error":
        raise JudgeUnavailableError()
    services.build_pipeline(repo, rules, settings).save_outcome(job, outcome, judge)
    if job.stage == "discarded":  # el veredicto se guarda, pero manda la guillotina
        repo.set_stage(job.id, "discarded")
    return views.to_item(repo, find_job(repo, job_id), utcnow())


@api.post("/jobs/{job_id}/handoff", response_model=Handoff)
async def handoff(job_id: str, request: Request, repo: RepoDep, settings: SettingsDep) -> Handoff:
    """Prepara el texto para el Optimizador. Si la descripción es un extracto, intenta leer la oferta
    completa con Jina Reader. Solo si queda completa se marca como enviada."""
    job = find_job(repo, job_id)
    description = job.facts.description
    if len(description.strip()) < views.OPTIMIZER_MIN_CHARS and job.url:
        api_key = settings.jina_api_key.get_secret_value() if settings.jina_api_key else None
        try:
            description = await extract_job_offer(
                request.app.state.http_client, job.url, min_chars=views.OPTIMIZER_MIN_CHARS, api_key=api_key
            )
        except AppError as exc:
            logger.info("handoff_fetch_failed job=%s code=%s", job.id[:8], exc.code)
    result = views.build_handoff(job, description)
    if result.complete:
        repo.set_app_status(job.id, "sent_to_optimizer")
    return result


# --- Aplicación --------------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=True
        ) as client:
            app.state.http_client = client
            yield
            task: asyncio.Task | None = app.state.run_task
            if task is not None and not task.done():
                task.cancel()

    app = FastAPI(title="Job Hunter (API local)", version=__version__, lifespan=lifespan, redoc_url=None)
    app.state.settings = settings
    app.state.run_task = None
    app.state.run_pending = None

    register_exception_handlers(app)
    app.add_exception_handler(RulesInvalidError, _rules_invalid)
    app.include_router(public)
    app.include_router(api)

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        # Chrome pide permiso para que una web pública (Vercel) llame a 127.0.0.1
        # (Private Network Access): Starlette responde al preflight si se activa.
        allow_private_network=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Hunter-Token"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    return app
