from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMOptimizeOutput(BaseModel):
    """Lo que esperamos que devuelva el LLM (se valida antes de usarlo)."""

    model_config = ConfigDict(extra="ignore")

    optimized_markdown: str = Field(min_length=50)
    job_keywords: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    changes_summary: list[str] = Field(default_factory=list)

    @field_validator("job_keywords", "gaps", "changes_summary", mode="before")
    @classmethod
    def _clean_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]


class MatchReport(BaseModel):
    score_before: int = Field(ge=0, le=100)
    score_after: int = Field(ge=0, le=100)
    matched_keywords: list[str]
    missing_keywords: list[str]


class ValidationWarning(BaseModel):
    code: Literal[
        "UNGROUNDED_DATE",
        "UNGROUNDED_METRIC",
        "UNGROUNDED_ENTITY",
        "UNGROUNDED_SKILL",
        "UNGROUNDED_CLAIM",
        "GAP_LEAKED",
        "FORMAT",
        "LIMITED_CHECK",
    ]
    message: str
    term: str | None = None  # fragmento exacto a resaltar en la vista previa
    snippet: str | None = None  # línea del CV optimizado donde aparece


class TokenUsageOut(BaseModel):
    input: int
    output: int


class OptimizeMeta(BaseModel):
    mode: Literal["server", "byok"]
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    tokens: TokenUsageOut
    pdf_pages: int


class OptimizeResponse(BaseModel):
    request_id: str | None
    optimized_markdown: str
    match: MatchReport
    gaps: list[str]
    changes_summary: list[str]
    warnings: list[ValidationWarning]
    # Expresiones reformuladas respecto al CV original (solo para resaltarlas en la interfaz).
    changes: list[str] = Field(default_factory=list)
    # "needs_review" si, tras el intento de corrección, sigue habiendo datos no respaldados.
    quality: Literal["ok", "needs_review"]
    meta: OptimizeMeta


class KeyValidationResponse(BaseModel):
    valid: bool
    provider: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    server_llm_available: bool


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
