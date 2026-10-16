"""Salida del juez IA (SPEC §4.1 y §7.3).

Dos niveles:
- `LLMVerdict`: lo que se pide al modelo. Tipos y enums estrictos, sin límites de longitud: el
  esquema que se envía a Groq solo usa palabras clave que el modo estricto admite seguro.
- `JobVerdict`: lo que se guarda y ve la UI. Se construye con `finalize()`, que recorta, acota,
  verifica las citas contra la oferta y corrige incoherencias. Nunca contiene null en las listas.
"""

import copy
import re
from typing import Any, Literal

from app.services.text_utils import fold
from pydantic import BaseModel, ConfigDict, Field

MAX_FLAGS = 6
MAX_STACK = 12
MAX_MISSING = 8
FLAG_TEXT_MAX = 160
EVIDENCE_MAX = 200
SUMMARY_MAX = 280

Verdict = Literal["apply", "maybe", "skip"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
SeniorityFit = Literal["under", "fit", "over", "unknown"]


class LLMFlag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    evidence: str


class LLMVerdict(BaseModel):
    """Esquema que se pide al modelo (todas las claves obligatorias)."""

    model_config = ConfigDict(extra="ignore")

    match_score: int
    verdict: Verdict
    summary: str
    green_flags: list[LLMFlag]
    red_flags: list[LLMFlag]
    stack_core: list[str]
    stack_inflated: list[str]
    missing_must_haves: list[str]
    seniority_detected: Seniority
    seniority_fit: SeniorityFit


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=FLAG_TEXT_MAX)
    evidence: str = Field(default="", max_length=EVIDENCE_MAX)
    evidence_verified: bool = False  # lo calcula el backend, nunca el LLM


class JobVerdict(BaseModel):
    """Veredicto final. Todos los campos siempre presentes."""

    model_config = ConfigDict(extra="forbid")

    match_score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary: str = Field(max_length=SUMMARY_MAX)
    green_flags: list[Flag] = Field(default_factory=list, max_length=MAX_FLAGS)
    red_flags: list[Flag] = Field(default_factory=list, max_length=MAX_FLAGS)
    stack_core: list[str] = Field(default_factory=list, max_length=MAX_STACK)
    stack_inflated: list[str] = Field(default_factory=list, max_length=MAX_STACK)
    missing_must_haves: list[str] = Field(default_factory=list, max_length=MAX_MISSING)
    seniority_detected: Seniority = "unknown"
    seniority_fit: SeniorityFit = "unknown"


# --- Esquema estricto para Structured Outputs -----------------------------------------------

# Palabras clave que se conservan: estructura y tipos. Los límites (maxLength, minimum...) los
# aplica finalize(), así un modelo que se pase de largo no hace fallar la petición.
_KEEP = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "additionalProperties",
    "$defs",
    "$ref",
    "description",
    "anyOf",
    "const",
}


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Esquema JSON apto para `strict: true`: todas las propiedades obligatorias,
    `additionalProperties: false` y sin títulos ni restricciones de longitud."""

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: clean(v) for k, v in node.items() if k in _KEEP - {"properties", "$defs"}}
            # En "properties" y "$defs" las claves son nombres, no palabras clave: no se filtran.
            if "properties" in node:
                out["properties"] = {k: clean(v) for k, v in node["properties"].items()}
            if "$defs" in node:
                out["$defs"] = {k: clean(v) for k, v in node["$defs"].items()}
            if out.get("type") == "object" and "properties" in out:
                out["required"] = list(out["properties"])
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [clean(x) for x in node]
        return node

    return clean(copy.deepcopy(model.model_json_schema()))


def response_format(model: type[BaseModel] = LLMVerdict, strict: bool = True) -> dict[str, Any]:
    return {"name": "job_verdict", "strict": strict, "schema": to_strict_schema(model)}


# --- Post-validación determinista ------------------------------------------------------------

_SPACES = re.compile(r"\s+")
_QUOTES = re.compile(r"[\"'«»“”‘’`]")


def _norm(text: str) -> str:
    return _SPACES.sub(" ", _QUOTES.sub("", fold(text))).strip(" .…")


def evidence_in(description_norm: str, evidence: str) -> bool:
    """¿La cita aparece literalmente en la oferta? Sin tildes, mayúsculas, comillas ni espacios
    extra. Citas de menos de 12 caracteres no cuentan: "Python" no prueba nada."""
    quote = _norm(evidence)
    return len(quote) >= 12 and quote in description_norm


def _clip(text: str, limit: int) -> str:
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _terms(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = _clip(value, 60)
        key = fold(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out[:limit]


def _flags(flags: list[LLMFlag], description_norm: str) -> list[Flag]:
    out: list[Flag] = []
    seen: set[str] = set()
    for flag in flags:
        text = _clip(flag.text, FLAG_TEXT_MAX)
        if not text or fold(text) in seen:
            continue
        seen.add(fold(text))
        evidence = _clip(flag.evidence, EVIDENCE_MAX)
        out.append(
            Flag(text=text, evidence=evidence, evidence_verified=evidence_in(description_norm, evidence))
        )
    return out[:MAX_FLAGS]


def finalize(raw: LLMVerdict, description: str) -> JobVerdict:
    """Recorta y acota lo que devuelve el modelo, verifica las citas y corrige incoherencias
    (el estilo se tolera, los hechos no: mismo criterio que ADR-010)."""
    description_norm = _norm(description)
    score = max(0, min(100, raw.match_score))
    verdict = raw.verdict
    if verdict == "apply" and score < 50:
        verdict = "maybe"
    elif verdict == "skip" and score >= 75:
        verdict = "maybe"
    return JobVerdict(
        match_score=score,
        verdict=verdict,
        summary=_clip(raw.summary, SUMMARY_MAX),
        green_flags=_flags(raw.green_flags, description_norm),
        red_flags=_flags(raw.red_flags, description_norm),
        stack_core=_terms(raw.stack_core, MAX_STACK),
        stack_inflated=_terms(raw.stack_inflated, MAX_STACK),
        missing_must_haves=_terms(raw.missing_must_haves, MAX_MISSING),
        seniority_detected=raw.seniority_detected,
        seniority_fit=raw.seniority_fit,
    )


def rank_score(match_score: int, prescore: int) -> float:
    """Manda la nota del juez; el pre-score (palabras clave) solo desempata.

    Antes era 0,8·nota + 0,2·pre-score, y en el primer run real un "quizá" de 60 con pre-score 100
    quedaba por encima de tres "aplicar" de 78."""
    return round(match_score + prescore / 1000, 3)
