"""Juez semántico (SPEC §7): puntúa el encaje de una oferta con el perfil, en Groq.

Flujo por oferta:
1. Caché: si ya existe un veredicto para (texto de la oferta, perfil, prompt, familia de modelo),
   se reutiliza sin llamar al LLM.
2. Llamada con Structured Outputs (esquema estricto de `LLMVerdict`), protegida por el presupuesto
   diario y el limitador de rate limits. Si Groq rechaza el esquema, se sigue con json_mode.
3. Validación con Pydantic. Si falla, UNA llamada de reparación con el error concreto.
4. `finalize()`: recorta, acota, verifica las citas y corrige incoherencias.
5. Si aun así no hay JSON válido: `judge_failed` (la oferta se ve sin puntuación, nada se rompe).
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Literal

from app.core.exceptions import (
    AppError,
    ByokKeyInvalidError,
    LLMBadOutputError,
    LLMUpstreamError,
    UpstreamRateLimitedError,
)
from app.services.llm.base import ChatMessage, LLMProvider, LLMRequest, LLMResponse
from app.services.text_utils import fold
from pydantic import ValidationError

from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard, QuotaExhaustedError, estimate_tokens
from hunter.judge.schema import JobVerdict, LLMVerdict, finalize, response_format
from hunter.pipeline.experience import required_years
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, StoredJob, StoredVerdict, utcnow

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v2"
_PLACEHOLDER = re.compile(r"\{\{(PROFILE|PRIORITIES|SOFT_DISLIKES|SIGNALS|JOB_OFFER|ERROR)\}\}")
# Nadie puede "cerrar" un bloque de datos desde dentro e inyectar instrucciones.
_DELIMITER = re.compile(r"<\s*(/?)\s*(job_offer|profile|signals)\s*>", re.IGNORECASE)
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
PROFILE_MAX_CHARS = 4000


@lru_cache
def _template(name: str) -> str:
    return (
        resources.files("hunter")
        .joinpath("prompts", f"{name}.{PROMPT_VERSION}.md")
        .read_text(encoding="utf-8")
    )


def _fill(template: str, values: dict[str, str]) -> str:
    # Una sola pasada: un "{{PROFILE}}" escrito dentro de la oferta no se expande.
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), template)


def escape_data(text: str) -> str:
    return _DELIMITER.sub(lambda m: f"[{m.group(1)}{m.group(2)}]", text)


def truncate_paragraphs(text: str, limit: int) -> str:
    """Recorta por párrafo (o por línea) para no partir frases a la mitad."""
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit)
    if cut < limit * 0.6:
        cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > 0 else limit].rstrip() + "\n[…oferta recortada]"


def model_family(model: str) -> str:
    """'openai/gpt-oss-120b' y 'openai/gpt-oss-20b' comparten caché: 'gpt-oss'."""
    name = model.split("/")[-1].lower()
    return re.sub(r"[-_]?\d+(?:\.\d+)?[bm]$", "", name) or name


@dataclass(frozen=True)
class JudgeContext:
    """Lo que el juez sabe del candidato. Si cambia, los veredictos en caché dejan de valer."""

    profile: str
    priorities: tuple[str, ...] = ()
    soft_dislikes: tuple[str, ...] = ()

    @classmethod
    def from_rules(cls, rules: GoldenRules, profile_text: str) -> "JudgeContext":
        return cls(profile_text.strip(), tuple(rules.judge.priorities), tuple(rules.judge.soft_dislikes))

    @property
    def hash(self) -> str:
        norm = re.sub(r"\s+", " ", fold(self.profile))
        raw = "|".join([norm, *map(fold, self.priorities), "#", *map(fold, self.soft_dislikes)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class JudgeConfig:
    model: str = "openai/gpt-oss-120b"
    max_input_chars: int = 6000
    max_output_tokens: int = 2048
    expected_output_tokens: int = 900  # para estimar el coste antes de llamar
    temperature: float = 0.2
    use_schema: bool = True


OutcomeStatus = Literal["ok", "cache_hit", "judge_failed", "error"]


@dataclass
class JudgeOutcome:
    status: OutcomeStatus
    cache_key: str
    verdict: JobVerdict | None = None
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


class JudgeStoppedError(Exception):
    """No tiene sentido seguir juzgando en esta ejecución (cuota, presupuesto o clave)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class _Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    responses: list[LLMResponse] = field(default_factory=list)

    def add(self, response: LLMResponse) -> None:
        self.tokens_in += response.usage.input
        self.tokens_out += response.usage.output
        self.model = response.model
        self.responses.append(response)


class Judge:
    def __init__(
        self,
        provider: LLMProvider,
        repo: Repository,
        limiter: AdaptiveLimiter,
        budget: BudgetGuard,
        context: JudgeContext,
        config: JudgeConfig | None = None,
    ) -> None:
        self.provider = provider
        self.repo = repo
        self.limiter = limiter
        self.budget = budget
        self.context = context
        self.config = config or JudgeConfig()
        self._family = model_family(self.config.model)

    # --- API pública ---------------------------------------------------------------------

    def cache_key(self, job: StoredJob) -> str:
        raw = f"{job.desc_sha256}|{self.context.hash}|{PROMPT_VERSION}|{self._family}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def cached(self, job: StoredJob) -> JudgeOutcome | None:
        key = self.cache_key(job)
        stored = self.repo.cached_verdict(key)
        if stored is None or stored.status != "ok" or not stored.verdict_json:
            return None
        try:
            verdict = JobVerdict.model_validate_json(stored.verdict_json)
        except ValidationError:
            return None
        return JudgeOutcome("cache_hit", key, verdict, model=stored.model)

    async def judge(self, job: StoredJob, force: bool = False) -> JudgeOutcome:
        """Nunca lanza salvo `JudgeStoppedError`. Los errores transitorios vuelven como 'error'."""
        if not force and (hit := self.cached(job)) is not None:
            return hit
        key = self.cache_key(job)
        usage = _Usage()
        messages = self.messages(job)
        try:
            content: str | None = None
            try:
                response = await self._call(messages, usage)
                content = response.content
                verdict = self._parse(content, job)
            except (ValidationError, ValueError, LLMBadOutputError) as exc:
                logger.info("judge_bad_output job=%s error=%s", job.id[:8], _short(exc))
                repair = [*messages]
                if content is not None:
                    repair.append(ChatMessage("assistant", content))
                repair.append(ChatMessage("user", _fill(_template("judge_repair"), {"ERROR": _short(exc)})))
                try:
                    verdict = self._parse((await self._call(repair, usage)).content, job)
                except (ValidationError, ValueError, LLMBadOutputError) as exc2:
                    return JudgeOutcome(
                        "judge_failed",
                        key,
                        None,
                        usage.model,
                        usage.tokens_in,
                        usage.tokens_out,
                        f"JSON no válido tras reparar: {_short(exc2)}",
                    )
        except (JudgeStoppedError, QuotaExhaustedError):
            raise
        except AppError as exc:
            logger.warning("judge_error job=%s code=%s", job.id[:8], exc.code)
            return JudgeOutcome("error", key, None, usage.model, usage.tokens_in, usage.tokens_out, exc.code)
        return JudgeOutcome("ok", key, verdict, usage.model, usage.tokens_in, usage.tokens_out)

    def record(self, outcome: JudgeOutcome) -> StoredVerdict:
        return StoredVerdict(
            cache_key=outcome.cache_key,
            status="ok" if outcome.verdict is not None else "judge_failed",
            verdict_json=outcome.verdict.model_dump_json() if outcome.verdict else None,
            model=outcome.model or self.config.model,
            prompt_version=PROMPT_VERSION,
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            created_at=utcnow(),
        )

    # --- Construcción del prompt ---------------------------------------------------------

    def messages(self, job: StoredJob) -> list[ChatMessage]:
        offer = (
            f"Título: {job.title}\nEmpresa: {job.company}\nUbicación: {job.location or 'no indicada'}\n\n"
            + truncate_paragraphs(job.facts.description, self.config.max_input_chars)
        )
        values = {
            "PROFILE": escape_data(truncate_paragraphs(self.context.profile, PROFILE_MAX_CHARS)),
            "PRIORITIES": escape_data("; ".join(self.context.priorities) or "no indicadas"),
            "SOFT_DISLIKES": escape_data("; ".join(self.context.soft_dislikes) or "nada en concreto"),
            "SIGNALS": escape_data(signals(job)),
            "JOB_OFFER": escape_data(offer),
        }
        return [
            ChatMessage("system", _template("judge_system")),
            ChatMessage("user", _fill(_template("judge_user"), values)),
        ]

    # --- Llamada protegida ---------------------------------------------------------------

    async def _call(self, messages: list[ChatMessage], usage: _Usage) -> LLMResponse:
        cost = estimate_tokens("".join(m.content for m in messages)) + self.config.expected_output_tokens
        self.budget.check(cost)
        await self.limiter.acquire(cost)
        request = LLMRequest(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_output_tokens,
            json_mode=True,
            json_schema=response_format() if self.config.use_schema else None,
        )
        try:
            response = await self.provider.complete(request)
        except UpstreamRateLimitedError as exc:
            # GroqProvider ya reintentó y probó el modelo de reserva: la cuota está agotada.
            self.limiter.observe_rate_limited(exc.retry_after_s)
            raise JudgeStoppedError("rate_limit", f"Groq pide esperar {exc.retry_after_s or '?'} s") from exc
        except ByokKeyInvalidError as exc:
            raise JudgeStoppedError("invalid_key", "GROQ_API_KEY no es válida") from exc
        except LLMUpstreamError:
            if not self.config.use_schema:
                raise
            # Groq rechazó la petición: lo más probable, que el modelo no admita el esquema estricto.
            logger.warning("judge_schema_rejected model=%s; sigo con json_mode", self.config.model)
            self.config.use_schema = False
            return await self._call(messages, usage)
        used = response.usage.input + response.usage.output
        self.limiter.observe(response.rate_limits, used)
        self.budget.add(used)
        usage.add(response)
        return response

    @staticmethod
    def _parse(content: str, job: StoredJob) -> JobVerdict:
        raw = LLMVerdict.model_validate_json(_CODE_FENCE.sub("", content))
        return finalize(raw, job.facts.description)


def signals(job: StoredJob, now: datetime | None = None) -> str:
    """Datos deterministas que ya tiene el sistema; el juez no tiene que adivinarlos."""
    now = now or utcnow()
    facts = job.facts
    years = required_years(facts.description).years
    published = facts.date_posted or job.first_seen.date()
    lines = [
        f"Modalidad detectada: {facts.modality}",
        f"Ubicación normalizada: {facts.location_bucket}",
        f"Años de experiencia exigidos (detectados): {years if years is not None else 'no indicados'}",
        f"Publicada hace {(now.date() - published).days} días; vista {job.times_seen} veces",
        f"Pre-score por palabras clave del perfil: {job.prescore}/100",
    ]
    return "\n".join(lines)


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", ()))
        return f"{len(errors)} error(es); {where}: {first.get('msg', '')}"[:200]
    return str(exc)[:200]
