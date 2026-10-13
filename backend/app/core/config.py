"""Configuración de la aplicación (Twelve-Factor: todo por variables de entorno)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    # --- LLM (Groq) ---
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Modelos de producción disponibles en el plan gratuito/developer de Groq (octubre de 2026).
    # Los Llama 3.x pasaron a ser "Enterprise". Lista actual: https://console.groq.com/docs/models
    groq_model_primary: str = "openai/gpt-oss-120b"
    groq_model_fallback: str | None = "openai/gpt-oss-20b"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2
    llm_backoff_base_s: float = 1.0
    llm_temperature: float = 0.2
    # En los modelos de razonamiento, el "pensamiento" también consume tokens de salida.
    llm_max_output_tokens: int = 8192
    # Solo se envía a modelos de razonamiento (gpt-oss). "low" basta para reescribir un CV y
    # reduce latencia y coste. Vacío = no enviar el parámetro.
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = "low"

    # --- Validador anti-alucinación ---
    # Si el CV generado tiene al menos N datos no respaldados, se pide al LLM una corrección.
    validator_correction_threshold: int = 1
    validator_max_corrections: int = 1

    # --- CORS ---
    # Lista separada por comas. En producción: la URL de Vercel.
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Opcional: regex para las previews de Vercel, p. ej. https://cv-optimizer-.*\.vercel\.app
    allowed_origin_regex: str | None = None

    # --- Límites de entrada ---
    max_upload_mb: int = 5
    max_pdf_pages: int = 5
    pdf_extraction_timeout_s: float = 10.0
    cv_min_chars: int = 200
    cv_max_chars: int = 30_000
    job_offer_min_chars: int = 200
    job_offer_max_chars: int = 15_000

    # --- Ofertas desde URL (Jina Reader) ---
    # Sin clave, Jina limita por IP (unas 20 peticiones/minuto); con clave el límite es mayor.
    jina_api_key: SecretStr | None = None
    job_url_timeout_s: float = 8.0
    job_url_per_minute: int = 10

    # --- Rate limiting (solo modo servidor) ---
    rate_limit_per_minute: int = 5
    rate_limit_per_day: int = 30
    key_validation_per_minute: int = 10

    @field_validator("groq_api_key", "jina_api_key", mode="before")
    @classmethod
    def _strip_api_key(cls, value: object) -> object:
        # Los paneles de los proveedores cloud (p. ej. el textarea de Render) cuelan a menudo
        # un salto de línea o un espacio al pegar la clave, y eso invalida la cabecera HTTP.
        return value.strip() if isinstance(value, str) else value

    @field_validator("llm_reasoning_effort", mode="before")
    @classmethod
    def _empty_reasoning_effort(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        # PDF + oferta (hasta 4 bytes por carácter UTF-8) + overhead del multipart.
        return self.max_upload_bytes + self.job_offer_max_chars * 4 + 64 * 1024

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def server_api_key(self) -> SecretStr | None:
        """Clave del servidor, o None si no está configurada (o está vacía)."""
        if self.groq_api_key is None or not self.groq_api_key.get_secret_value().strip():
            return None
        return self.groq_api_key

    @property
    def groq_models(self) -> list[str]:
        models = [self.groq_model_primary]
        if self.groq_model_fallback and self.groq_model_fallback != self.groq_model_primary:
            models.append(self.groq_model_fallback)
        return models


@lru_cache
def get_settings() -> Settings:
    return Settings()
