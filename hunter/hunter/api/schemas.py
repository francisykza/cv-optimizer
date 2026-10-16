"""Contratos JSON de la API local (SPEC §8). Las listas nunca son null: la UI no tiene que comprobarlo."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hunter.judge.schema import JobVerdict
from hunter.models import (
    ApplicationEvent,
    ApplicationSource,
    ApplicationStatus,
    AppStatus,
    Modality,
    Run,
    RunMode,
    Stage,
    optional_http_url,
)
from hunter.pipeline.simulate import SimulationReport
from hunter.rules.schema import GoldenRules


class LastRun(BaseModel):
    id: str
    status: str
    finished_at: datetime | None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    db_ok: bool
    groq_key_configured: bool
    token_configured: bool
    last_run: LastRun | None = None
    # Minutos sin uso tras los que se apaga sola (None: arrancada a mano, no se apaga).
    auto_shutdown_minutes: int | None = None


class RulesVersion(BaseModel):
    version: str
    created_at: datetime
    active: bool


class RulesResponse(BaseModel):
    version: str
    rules: GoldenRules
    history: list[RulesVersion] = Field(default_factory=list)


class RulesUpdate(BaseModel):
    rules: GoldenRules


class RulesSaved(BaseModel):
    version: str
    reevaluated: int
    now_pending_judge: int
    now_discarded: int


class SimulateRequest(BaseModel):
    rules: GoldenRules
    window_days: int = Field(default=7, ge=1, le=90)


SimulateResponse = SimulationReport


class RunRequest(BaseModel):
    mode: RunMode = "full"
    only: list[str] | None = None
    judge_limit: int | None = Field(default=None, ge=1, le=500)
    retry_failed: bool = False


class RunAccepted(BaseModel):
    run_id: str
    status: Literal["running"] = "running"


class RunsResponse(BaseModel):
    items: list[Run]


class SourceHealthOut(BaseModel):
    source: str
    state: Literal["closed", "open", "half_open"]
    consecutive_failures: int
    open_until: datetime | None
    last_ok_at: datetime | None
    last_error: str | None


class SourceLink(BaseModel):
    site: str
    url: str


class GuillotineOut(BaseModel):
    rule_id: str | None
    rule_label: str | None
    matched_text: str | None


JudgeStatus = Literal["ok", "judge_failed", "pending", "discarded"]


class JobItem(BaseModel):
    id: str
    title: str
    company: str
    location: str
    modality: Modality
    stage: Stage
    app_status: AppStatus
    rank_score: float | None
    prescore: int
    first_seen: datetime
    times_seen: int
    days_published: int
    sources: list[SourceLink] = Field(default_factory=list)
    verdict: JobVerdict | None = None
    judge_status: JudgeStatus
    judge_error: str | None = None
    guillotine: GuillotineOut | None = None


class VerdictHistoryItem(BaseModel):
    model: str
    prompt_version: str
    created_at: datetime
    match_score: int | None


class JobDetail(JobItem):
    description: str
    verdict_history: list[VerdictHistoryItem] = Field(default_factory=list)


JobsView = Literal["ranked", "pending", "discarded", "failed", "all"]


class JobsPage(BaseModel):
    items: list[JobItem]
    total: int
    next_cursor: str | None = None


class AppStatusUpdate(BaseModel):
    app_status: AppStatus


class Handoff(BaseModel):
    """Lo que la vista Buscador deja en sessionStorage['cvopt:handoff'] para el Optimizador."""

    version: Literal[1] = 1
    text: str
    chars: int
    title: str
    company: str
    source_url: str | None
    language: Literal["es", "en"] | None
    complete: bool


# --- Fase 4: emparejado, candidaturas y apagado (SPEC §18) --------------------------------------


class PairRequest(BaseModel):
    code: str = Field(min_length=8, max_length=128)


class PairResponse(BaseModel):
    token: str


class ApplicationItem(BaseModel):
    """Candidatura en los listados: sin la copia de la oferta ni el CV (`has_*` dicen si existen)."""

    id: str
    job_id: str | None
    company: str
    title: str
    url: str | None
    location: str
    source: ApplicationSource
    status: ApplicationStatus
    applied_at: datetime
    status_changed_at: datetime
    ats_score_before: int | None
    ats_score_after: int | None
    judge_score: int | None
    notes: str
    has_offer_text: bool
    has_cv: bool
    events: list[ApplicationEvent] = Field(default_factory=list)
    # Enviada hace más de 3 semanas sin noticias: la UI propone marcarla "sin respuesta".
    stale: bool = False


class ApplicationDetail(ApplicationItem):
    offer_text: str | None
    cv_markdown: str | None


class ApplicationUpdate(BaseModel):
    """Solo se cambian los campos enviados. `url` vacía o null la borra."""

    model_config = ConfigDict(str_strip_whitespace=True)

    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2048)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        return optional_http_url(value)

    def changes(self) -> dict[str, object]:
        sent = self.model_dump(exclude_unset=True)
        return {k: v for k, v in sent.items() if v is not None or k == "url"}


class ScoreBand(BaseModel):
    """Candidaturas por tramo de compatibilidad del CV enviado, y cuántas recibieron respuesta."""

    label: str
    total: int
    responded: int


class ApplicationStats(BaseModel):
    total: int
    last_7_days: int
    awaiting: int  # enviadas, todavía sin respuesta
    responded: int  # la empresa contestó (en proceso, entrevista, oferta o rechazo)
    interviews: int  # llegaron a entrevista
    offers: int
    stale: int
    avg_ats_after: int | None
    by_band: list[ScoreBand] = Field(default_factory=list)


class ApplicationsPage(BaseModel):
    items: list[ApplicationItem]
    total: int
    stats: ApplicationStats


class ShutdownAccepted(BaseModel):
    status: Literal["stopping"] = "stopping"
