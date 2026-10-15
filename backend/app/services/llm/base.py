"""Contrato común para proveedores de LLM (patrón Strategy)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]
Mode = Literal["server", "byok"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMRequest:
    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: int = 4096
    json_mode: bool = False
    # Structured Outputs: {"name": ..., "schema": {...}, "strict": bool}. Tiene prioridad sobre
    # json_mode. Lo usa el juez del Job Hunter; el Optimizador sigue con json_mode.
    json_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class TokenUsage:
    input: int = 0
    output: int = 0


@dataclass(frozen=True)
class RateLimitInfo:
    """Cabeceras x-ratelimit-* del proveedor. En Groq, "requests" es la cuota diaria de peticiones
    y "tokens" la de tokens por minuto. None = el proveedor no la envió."""

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_s: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_s: float | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    rate_limits: RateLimitInfo | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Devuelve la respuesta del modelo o lanza un AppError del módulo de excepciones."""
