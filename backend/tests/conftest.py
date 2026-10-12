import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

GROQ_BASE = "https://api.groq.test/openai/v1"
SERVER_KEY = "gsk_server_key_0123456789abcdef"
USER_KEY = "gsk_user_key_abcdef0123456789xyz"
FRONTEND_ORIGIN = "http://localhost:5173"


def make_settings(**overrides) -> Settings:
    values = dict(
        groq_api_key=SERVER_KEY,
        groq_base_url=GROQ_BASE,
        groq_model_primary="primary-model",
        groq_model_fallback="fallback-model",
        llm_backoff_base_s=0,
        allowed_origins=FRONTEND_ORIGIN,
        rate_limit_per_minute=100,
        rate_limit_per_day=1000,
    )
    values.update(overrides)
    # _env_file=None: los tests no deben depender del .env local.
    return Settings(_env_file=None, **values)


def llm_payload(**overrides) -> dict:
    payload = {
        "optimized_markdown": (
            "# Ana Garcia Lopez\n\n## Resumen profesional\nDesarrolladora backend con Python, "
            "FastAPI y PostgreSQL.\n\n## Experiencia\n### Acme Software SL\n- APIs REST con FastAPI."
            "\n\n## Habilidades\nPython, FastAPI, PostgreSQL, Docker"
        ),
        "job_keywords": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Terraform", "Rust"],
        "gaps": ["Kubernetes", "Terraform", "Ingles C1 (el CV indica B2)"],
        "changes_summary": ["Resumen orientado a backend con Python."],
    }
    payload.update(overrides)
    return payload


def groq_completion(content: str | dict, model: str = "primary-model", status: int = 200) -> httpx.Response:
    if isinstance(content, dict):
        content = json.dumps(content)
    return httpx.Response(
        status,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 400},
        },
    )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def groq_mock():
    with respx.mock(base_url=GROQ_BASE, assert_all_called=False) as mock:
        yield mock
