"""Logging a stdout. Nunca se registran contenidos de usuario ni claves."""

import logging
import re

_SECRET_PATTERNS = [
    # Claves con prefijos conocidos (Groq, OpenAI, Anthropic).
    re.compile(r"\b(gsk_|sk-ant-|sk-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{8,}"),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Red de seguridad: si una clave acabara en un mensaje de log, se enmascara."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(RedactSecretsFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # httpx registra cada URL a nivel INFO; no aporta y añade ruido.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
