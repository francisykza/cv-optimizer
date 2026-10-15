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

    # --- LLM (Fase 2) ---
    groq_api_key: SecretStr | None = None
    jina_api_key: SecretStr | None = None

    @field_validator("groq_api_key", "jina_api_key", mode="before")
    @classmethod
    def _strip_api_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @property
    def db_path(self) -> Path:
        """Ruta absoluta: las relativas cuelgan de `hunter/`, no del directorio actual
        (el Programador de tareas de Windows arranca en System32)."""
        path = self.hunter_db_path
        return path if path.is_absolute() else HUNTER_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
