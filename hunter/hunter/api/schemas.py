"""Contratos JSON de la API local (SPEC §8). Las listas nunca son null: la UI no tiene que comprobarlo."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from hunter.judge.schema import JobVerdict
from hunter.models import AppStatus, Modality, Run, RunMode, Stage
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
