"""Modelos de datos del Job Hunter (SPEC §4.1). Pydantic es la fuente única de verdad."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Site = Literal["linkedin", "indeed", "google", "remotive", "arbeitnow", "rss"]
Modality = Literal["remote", "hybrid", "onsite", "unknown"]
Language = Literal["es", "en", "other", "unknown"]
Stage = Literal["discarded", "pending_judge", "judged", "judge_failed"]
AppStatus = Literal["none", "saved", "sent_to_optimizer", "applied", "dismissed"]
SalaryInterval = Literal["yearly", "monthly", "weekly", "daily", "hourly"]


class RawJob(BaseModel):
    """Lo que entrega una fuente, ya validado. Una fila que no valida se descarta y se cuenta."""

    model_config = ConfigDict(str_strip_whitespace=True)

    site: Site
    site_job_id: str | None = Field(default=None, max_length=200)
    url: str = Field(max_length=2048)
    title: str = Field(min_length=2, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=300)
    is_remote: bool | None = None
    date_posted: date | None = None
    description: str = Field(default="", max_length=60_000)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    salary_interval: SalaryInterval | None = None

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("La URL debe empezar por http:// o https://")
        return value


class NormalizedJob(BaseModel):
    """Oferta normalizada, lista para deduplicar y pasar por la guillotina."""

    raw: RawJob
    url_canonical: str
    title_norm: str
    company_norm: str
    location_bucket: str
    modality: Modality
    language: Language
    description: str  # limpia, para mostrar y para la guillotina
    job_key: str
    desc_sha256: str
    simhash: str  # 16 caracteres hex (64 bits)
    salary_annual_max: float | None = None  # en la moneda original, anualizado


class GuillotineResult(BaseModel):
    passed: bool
    rule_id: str | None = None
    rule_label: str | None = None
    matched_text: str | None = Field(default=None, max_length=200)
    rules_version: str


class RuleHit(BaseModel):
    """Una regla que descarta (en modo explicación se devuelven todas)."""

    rule_id: str
    rule_label: str
    matched_text: str | None = Field(default=None, max_length=200)


SourceStatus = Literal["ok", "empty", "blocked", "timeout", "error", "skipped_breaker_open"]


class SourceRun(BaseModel):
    source: str
    status: SourceStatus
    fetched: int = 0
    valid: int = 0
    invalid: int = 0
    duration_ms: int = 0
    error_code: str | None = None
    error_message: str | None = Field(default=None, max_length=500)
    retry_at: datetime | None = None


class RunCounts(BaseModel):
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    discarded: int = 0
    pending_judge: int = 0
    judged: int = 0
    judge_failed: int = 0
    cache_hits: int = 0
    # Ofertas en la cola del juez al empezar a juzgar: con judged + judge_failed da el progreso.
    judge_queue: int = 0


RunStatus = Literal["running", "ok", "partial", "failed"]
# rejudge: vuelve a juzgar las ofertas cuya nota es de un perfil anterior (SPEC §19.3).
RunMode = Literal["full", "ingest_only", "judge_only", "rejudge"]
RunTrigger = Literal["scheduler", "api", "cli"]


class Run(BaseModel):
    id: str
    trigger: RunTrigger
    mode: RunMode
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    rules_version: str
    counts: RunCounts = Field(default_factory=RunCounts)
    tokens_used: int = 0
    budget_exhausted: bool = False
    sources: list[SourceRun] = Field(default_factory=list)
    error: str | None = None


# --- Candidaturas (Fase 4, SPEC §18.4) ---------------------------------------------------------

ApplicationStatus = Literal[
    "applied", "in_process", "interview", "offer", "rejected", "no_response", "withdrawn"
]
ApplicationSource = Literal["optimizer", "hunter", "manual"]


def optional_http_url(value: str | None) -> str | None:
    """Vacía o None: sin URL. Si la hay, tiene que ser http(s), porque se muestra como enlace."""
    if not value:
        return None
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("La URL debe empezar por http:// o https://")
    return value


class ApplicationIn(BaseModel):
    """Alta de una candidatura. El id lo genera el cliente: si el navegador la reenvía desde su cola
    (la API estaba apagada), no se duplica."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    job_id: str | None = Field(default=None, max_length=64)
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2048)
    location: str = Field(default="", max_length=300)
    source: ApplicationSource = "manual"
    applied_at: datetime | None = None  # por defecto, ahora
    ats_score_before: int | None = Field(default=None, ge=0, le=100)
    ats_score_after: int | None = Field(default=None, ge=0, le=100)
    judge_score: int | None = Field(default=None, ge=0, le=100)
    notes: str = Field(default="", max_length=4000)
    offer_text: str | None = Field(default=None, max_length=20_000)
    cv_markdown: str | None = Field(default=None, max_length=40_000)

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        return optional_http_url(value)


class ApplicationEvent(BaseModel):
    status: ApplicationStatus
    at: datetime


class ApplicationRecord(BaseModel):
    """Candidatura guardada. En los listados, `offer_text` y `cv_markdown` no se cargan (son largos):
    `has_offer_text` y `has_cv` dicen si existen."""

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
    has_offer_text: bool = False
    has_cv: bool = False
    offer_text: str | None = None
    cv_markdown: str | None = None
    events: list[ApplicationEvent] = Field(default_factory=list)
