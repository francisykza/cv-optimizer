"""Proveedor LLM falso con respuestas programadas (nunca hay red en los tests)."""

import json
from collections.abc import Callable
from typing import Any

from app.services.llm.base import LLMProvider, LLMRequest, LLMResponse, RateLimitInfo, TokenUsage


def verdict_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "match_score": 82,
        "verdict": "apply",
        "summary": "Encaja por el stack de Python y LLM y por la mentoría explícita.",
        "green_flags": [{"text": "Mentoría con perfiles senior", "evidence": "mentoría de perfiles senior"}],
        "red_flags": [],
        "stack_core": ["Python", "FastAPI", "RAG"],
        "stack_inflated": [],
        "missing_must_haves": [],
        "seniority_detected": "junior",
        "seniority_fit": "fit",
    }
    payload.update(overrides)
    return payload


Step = str | dict | Exception | Callable[[LLMRequest], Any]


class FakeProvider(LLMProvider):
    """Cada llamada consume el siguiente paso: un dict (JSON válido), un str (contenido literal),
    una excepción (se lanza) o una función que recibe la petición."""

    name = "fake"

    def __init__(
        self,
        *steps: Step,
        model: str = "openai/gpt-oss-120b",
        repeat_last: bool = True,
        usage: tuple[int, int] = (1000, 300),
        rate_limits: RateLimitInfo | None = None,
    ) -> None:
        self.steps = list(steps)
        self.model = model
        self.repeat_last = repeat_last
        self.usage = usage
        self.rate_limits = rate_limits
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.steps:
            raise AssertionError("FakeProvider sin pasos programados")
        step = self.steps[0] if (self.repeat_last and len(self.steps) == 1) else self.steps.pop(0)
        if callable(step) and not isinstance(step, type):
            step = step(request)
        if isinstance(step, Exception):
            raise step
        content = json.dumps(step, ensure_ascii=False) if isinstance(step, dict) else step
        return LLMResponse(
            content=content, model=self.model, usage=TokenUsage(*self.usage), rate_limits=self.rate_limits
        )
