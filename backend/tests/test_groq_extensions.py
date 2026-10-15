"""Extensiones de GroqProvider que usa el Job Hunter (SPEC del hunter §14): structured outputs,
cabeceras de rate limit y Retry-After en el error. Sin efecto en el Optimizador si no se usan."""

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.core.exceptions import UpstreamRateLimitedError
from app.services.llm.base import ChatMessage, LLMRequest, RateLimitInfo
from app.services.llm.groq import GroqProvider, parse_duration, parse_rate_limits

BASE = "https://api.groq.test/openai/v1"
MESSAGES = [ChatMessage("user", "hola")]


def provider(client: httpx.AsyncClient, models: list[str] | None = None) -> GroqProvider:
    return GroqProvider(
        client=client, api_key=SecretStr("gsk_test_0123456789abcdef"), models=models or ["m1"],
        mode="byok", base_url=BASE, max_retries=0, backoff_base_s=0,
    )


def completion(headers: dict[str, str] | None = None) -> httpx.Response:
    body = {"model": "m1", "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    return httpx.Response(200, json=body, headers=headers or {})


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("7.66s", 7.66), ("2m59.56s", 179.56), ("1h2m3s", 3723.0), ("120ms", 0.12), ("30", 30.0),
     ("", None), (None, None), ("pronto", None)],
)
def test_parse_duration(value, seconds) -> None:
    result = parse_duration(value)
    assert result == pytest.approx(seconds) if seconds is not None else result is None


def test_parse_rate_limits() -> None:
    headers = httpx.Headers({
        "x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "998",
        "x-ratelimit-reset-requests": "2m52.8s", "x-ratelimit-limit-tokens": "8000",
        "x-ratelimit-remaining-tokens": "6500", "x-ratelimit-reset-tokens": "11.25s",
    })
    assert parse_rate_limits(headers) == RateLimitInfo(1000, 998, 172.8, 8000, 6500, 11.25)
    assert parse_rate_limits(httpx.Headers({})) is None


@respx.mock
async def test_json_schema_is_sent_as_structured_output() -> None:
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=completion())
    schema = {"name": "x", "strict": True, "schema": {"type": "object"}}
    async with httpx.AsyncClient() as client:
        await provider(client).complete(LLMRequest(MESSAGES, json_mode=True, json_schema=schema))
    sent = json.loads(route.calls.last.request.content)
    assert sent["response_format"] == {"type": "json_schema", "json_schema": schema}


@respx.mock
async def test_json_mode_unchanged_without_schema() -> None:
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=completion())
    async with httpx.AsyncClient() as client:
        await provider(client).complete(LLMRequest(MESSAGES, json_mode=True))
    assert json.loads(route.calls.last.request.content)["response_format"] == {"type": "json_object"}


@respx.mock
async def test_response_carries_rate_limits() -> None:
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=completion({"x-ratelimit-remaining-tokens": "123", "x-ratelimit-reset-tokens": "4s"})
    )
    async with httpx.AsyncClient() as client:
        response = await provider(client).complete(LLMRequest(MESSAGES))
    assert response.rate_limits == RateLimitInfo(remaining_tokens=123, reset_tokens_s=4.0)


@respx.mock
async def test_rate_limited_error_keeps_retry_after() -> None:
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(429, headers={"retry-after": "3600"}, json={"error": {}})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(UpstreamRateLimitedError) as exc:
            await provider(client).complete(LLMRequest(MESSAGES))
    assert exc.value.retry_after_s == 3600
