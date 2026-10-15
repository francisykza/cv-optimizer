"""Proveedor Groq (API compatible con OpenAI) sobre httpx, con reintentos y modelo de reserva."""

import asyncio
import logging
import random
import re

import httpx
from pydantic import SecretStr

from app.core.exceptions import (
    AppError,
    ByokKeyInvalidError,
    LLMBadOutputError,
    LLMTimeoutError,
    LLMUpstreamError,
    UpstreamRateLimitedError,
)
from app.services.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Mode,
    RateLimitInfo,
    TokenUsage,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)


def is_reasoning_model(model: str) -> bool:
    return model.startswith(_REASONING_MODEL_PREFIXES)
_MAX_RETRY_AFTER_S = 10.0
_CONNECT_TIMEOUT_S = 5.0


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        models: list[str],
        mode: Mode,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_s: float = 45.0,
        max_retries: int = 2,
        backoff_base_s: float = 1.0,
        reasoning_effort: str | None = None,
    ) -> None:
        if not models:
            raise ValueError("Se necesita al menos un modelo.")
        self._reasoning_effort = reasoning_effort
        self._client = client
        self._api_key = api_key  # SecretStr: su repr es '**********'
        self._models = models
        self._mode = mode
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_s, connect=_CONNECT_TIMEOUT_S)
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        last_error: AppError | None = None
        for model in self._models:
            try:
                return await self._complete_with_retries(model, request)
            except (UpstreamRateLimitedError, LLMUpstreamError) as exc:
                # Cuota agotada, 5xx persistente o modelo retirado: probamos el siguiente modelo.
                logger.warning("llm_model_failed provider=groq model=%s code=%s", model, exc.code)
                last_error = exc
        raise last_error or LLMUpstreamError()

    async def _complete_with_retries(self, model: str, request: LLMRequest) -> LLMResponse:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": request.json_schema}
        elif request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self._reasoning_effort and is_reasoning_model(model):
            # Solo los modelos de razonamiento aceptan este parámetro; al resto les daría un 400.
            payload["reasoning_effort"] = self._reasoning_effort

        error: AppError = LLMUpstreamError()
        for attempt in range(self._max_retries + 1):
            retry_after: float | None = None
            try:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=self._headers,
                    timeout=self._timeout,
                )
            except httpx.TimeoutException as exc:
                # No se reintenta: con 45 s por intento la espera total sería inaceptable.
                raise LLMTimeoutError() from exc
            except httpx.LocalProtocolError as exc:
                # La petición ni siquiera se envía (p. ej. cabecera inválida): reintentar no ayuda.
                logger.error("llm_invalid_request provider=groq error=%s", type(exc).__name__)
                raise LLMUpstreamError("La petición al proveedor de IA no es válida.") from exc
            except httpx.TransportError as exc:
                logger.warning(
                    "llm_transport_error provider=groq model=%s error=%s", model, type(exc).__name__
                )
                error = LLMUpstreamError("No se pudo conectar con el proveedor de IA.")
            else:
                if response.status_code == 200:
                    return self._parse(response, model)
                self._raise_if_not_retryable(response)
                retry_after = _parse_retry_after(response)
                error = (
                    UpstreamRateLimitedError(retry_after_s=retry_after)
                    if response.status_code == 429
                    else LLMUpstreamError()
                )
                if retry_after is not None and retry_after > _MAX_RETRY_AFTER_S:
                    break  # Esperar tanto no compensa: pasamos al modelo de reserva.

            if attempt < self._max_retries:
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                await asyncio.sleep(delay)
        raise error

    def _raise_if_not_retryable(self, response: httpx.Response) -> None:
        status = response.status_code
        if status in _RETRYABLE_STATUS:
            return
        if status in (401, 403):
            if self._mode == "byok":
                raise ByokKeyInvalidError()
            logger.error("llm_server_key_rejected provider=groq status=%s", status)
            raise LLMUpstreamError("El proveedor de IA rechazó la configuración del servidor.")

        error_code = _groq_error_code(response)
        if error_code == "json_validate_failed":
            # El modelo no generó JSON válido en json_mode; el orquestador puede reintentar.
            raise LLMBadOutputError()
        logger.warning("llm_request_rejected provider=groq status=%s code=%s", status, error_code)
        # Modelo retirado/inexistente, contexto excedido, etc. -> LLMUpstreamError permite fallback.
        raise LLMUpstreamError("El proveedor de IA rechazó la petición.")

    def _backoff(self, attempt: int) -> float:
        base = self._backoff_base_s * (2**attempt)
        return base + random.uniform(0, base / 2) if base > 0 else 0  # noqa: S311 (jitter, no cripto)

    @staticmethod
    def _parse(response: httpx.Response, model: str) -> LLMResponse:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMBadOutputError() from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMBadOutputError()
        return LLMResponse(
            content=content,
            model=data.get("model", model),
            usage=TokenUsage(
                input=int(usage.get("prompt_tokens", 0)),
                output=int(usage.get("completion_tokens", 0)),
            ),
            rate_limits=parse_rate_limits(response.headers),
        )


async def validate_groq_key(
    client: httpx.AsyncClient,
    api_key: SecretStr,
    base_url: str = "https://api.groq.com/openai/v1",
    timeout_s: float = 10.0,
) -> bool:
    """Comprueba una clave con una llamada barata (listar modelos), sin consumir tokens."""
    try:
        response = await client.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx.Timeout(timeout_s, connect=_CONNECT_TIMEOUT_S),
        )
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError("El proveedor de IA no respondió a tiempo.") from exc
    except httpx.TransportError as exc:
        raise LLMUpstreamError("No se pudo conectar con el proveedor de IA.") from exc

    if response.status_code == 200:
        return True
    if response.status_code in (401, 403):
        return False
    if response.status_code == 429:
        raise UpstreamRateLimitedError()
    raise LLMUpstreamError()


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(value: str | None) -> float | None:
    """Duraciones de Groq ("7.66s", "2m59.56s", "1h2m3s", "120ms") a segundos."""
    if not value:
        return None
    value = value.strip()
    parts = _DURATION_PART.findall(value)
    if not parts or "".join(n + u for n, u in parts) != value:
        try:
            return max(float(value), 0.0)  # sin unidades: segundos
        except ValueError:
            return None
    return sum(float(n) * _DURATION_UNITS[u] for n, u in parts)


def _header_int(headers: httpx.Headers, name: str) -> int | None:
    try:
        return int(float(headers[name]))
    except (KeyError, ValueError):
        return None


def parse_rate_limits(headers: httpx.Headers) -> RateLimitInfo | None:
    info = RateLimitInfo(
        limit_requests=_header_int(headers, "x-ratelimit-limit-requests"),
        remaining_requests=_header_int(headers, "x-ratelimit-remaining-requests"),
        reset_requests_s=parse_duration(headers.get("x-ratelimit-reset-requests")),
        limit_tokens=_header_int(headers, "x-ratelimit-limit-tokens"),
        remaining_tokens=_header_int(headers, "x-ratelimit-remaining-tokens"),
        reset_tokens_s=parse_duration(headers.get("x-ratelimit-reset-tokens")),
    )
    return None if info == RateLimitInfo() else info


def _groq_error_code(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error") or {}
        return error.get("code")
    except (ValueError, AttributeError):
        return None
