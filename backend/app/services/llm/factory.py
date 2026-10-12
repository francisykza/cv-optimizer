"""Selección del proveedor de LLM: clave del servidor (.env) o clave del usuario (BYOK)."""

import re

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import (
    InvalidApiKeyFormatError,
    InvalidProviderError,
    LLMNotConfiguredError,
)
from app.services.llm.base import LLMProvider
from app.services.llm.groq import GroqProvider

SUPPORTED_PROVIDERS = {"groq"}

# Solo caracteres imprimibles sin espacios; longitud razonable para cualquier proveedor.
_KEY_FORMAT = re.compile(r"^[\x21-\x7e]{20,300}$")


def parse_user_key(raw: str | None) -> SecretStr | None:
    """Normaliza la cabecera X-User-API-Key. Devuelve None si no viene o viene vacía."""
    if raw is None or not raw.strip():
        return None
    key = raw.strip()
    if not _KEY_FORMAT.match(key):
        raise InvalidApiKeyFormatError()
    return SecretStr(key)


def check_provider(provider: str | None) -> str:
    name = (provider or "groq").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise InvalidProviderError()
    return name


def create_provider(
    settings: Settings,
    client: httpx.AsyncClient,
    user_key: SecretStr | None,
) -> LLMProvider:
    common = dict(
        client=client,
        base_url=settings.groq_base_url,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        backoff_base_s=settings.llm_backoff_base_s,
        reasoning_effort=settings.llm_reasoning_effort,
    )
    if user_key is not None:
        # BYOK: la clave del usuario solo vive en este objeto, durante esta petición.
        return GroqProvider(
            api_key=user_key, models=[settings.groq_model_primary], mode="byok", **common
        )

    server_key = settings.server_api_key
    if server_key is None:
        raise LLMNotConfiguredError()
    return GroqProvider(api_key=server_key, models=settings.groq_models, mode="server", **common)
