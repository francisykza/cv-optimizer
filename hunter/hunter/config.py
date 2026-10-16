"""Configuración del Job Hunter (Twelve-Factor: variables de entorno o `hunter/.env`)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del paquete `hunter/` (donde viven .env, data/ y rules.example.json).
HUNTER_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=HUNTER_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"

    # --- API local (Fase 3) ---
    hunter_host: str = "127.0.0.1"
    hunter_port: int = 8001
    hunter_token: SecretStr | None = None  # lo genera `python -m hunter init`
    # Orígenes del frontend que pueden llamar a la API (separados por comas).
    hunter_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Persistencia ---
    hunter_db_path: Path = Path("data/hunter.db")
    hunter_retention_days: int = 90

    # --- Fuentes ---
    hunter_source_timeout_s: float = 90.0
    hunter_breaker_threshold: int = 3
    hunter_breaker_cooldown_h: float = 6.0
    hunter_breaker_max_cooldown_h: float = 48.0
    # Pausa entre búsquedas consecutivas en el mismo portal (segundos, con jitter).
    hunter_source_pause_s: tuple[float, float] = (3.0, 8.0)

    # --- Deduplicación ---
    hunter_dedup_window_days: int = 60

    # --- Juez IA (Fase 2) ---
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Llama 3.x es Enterprise desde octubre de 2026: mismos modelos que el backend.
    groq_model_primary: str = "openai/gpt-oss-120b"
    groq_model_fallback: str | None = "openai/gpt-oss-20b"
    hunter_reasoning_effort: str | None = "low"
    hunter_judge_timeout_s: float = 60.0
    hunter_judge_max_input_chars: int = 6000
    # En gpt-oss el razonamiento también consume tokens de salida.
    hunter_judge_max_output_tokens: int = 2048
    # Tope propio de tokens/día (ajústalo a la cuota real de tu plan en console.groq.com).
    hunter_daily_token_budget: int = 150_000
    # Punto de partida del limitador; se ajusta solo con las cabeceras x-ratelimit-* de Groq.
    hunter_tokens_per_minute: int = 6000
    jina_api_key: SecretStr | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.hunter_allowed_origins.split(",") if o.strip()]

    @field_validator("groq_api_key", "jina_api_key", "hunter_token", mode="before")
    @classmethod
    def _strip_api_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("hunter_reasoning_effort", "groq_model_fallback", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def server_api_key(self) -> SecretStr | None:
        key = self.groq_api_key
        return key if key is not None and key.get_secret_value().strip() else None

    @property
    def groq_models(self) -> list[str]:
        models = [self.groq_model_primary]
        if self.groq_model_fallback and self.groq_model_fallback != self.groq_model_primary:
            models.append(self.groq_model_fallback)
        return models

    @property
    def db_path(self) -> Path:
        """Ruta absoluta: las relativas cuelgan de `hunter/`, no del directorio actual
        (el Programador de tareas de Windows arranca en System32)."""
        path = self.hunter_db_path
        return path if path.is_absolute() else HUNTER_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
