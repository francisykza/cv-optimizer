"""Contrato común para proveedores de LLM (patrón Strategy)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

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


@dataclass(frozen=True)
class TokenUsage:
    input: int = 0
    output: int = 0


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Devuelve la respuesta del modelo o lanza un AppError del módulo de excepciones."""
