"""Emparejado del navegador (SPEC §18.2).

El lanzador crea un código de un solo uso y abre la web con él en la URL (`#/buscar?pair=...`); la
web lo canjea en `POST /api/v1/pair` por el token local y lo recuerda. Así nadie tiene que copiar el
token de `hunter/.env`. El código caduca a los 2 minutos, sirve una sola vez y solo se guarda su hash:
aunque quede en el historial del navegador, ya no vale para nada.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from hunter.store.repository import Repository, utcnow

MAX_CODE_CHARS = 128


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def new_code(repo: Repository, ttl_s: int, now: datetime | None = None) -> str:
    code = secrets.token_urlsafe(24)
    repo.create_pairing_code(_digest(code), (now or utcnow()) + timedelta(seconds=ttl_s))
    return code


def redeem(repo: Repository, code: str, now: datetime | None = None) -> bool:
    """True si el código existía y no había caducado. En cualquier caso deja de valer."""
    if not code or len(code) > MAX_CODE_CHARS:
        return False
    return repo.consume_pairing_code(_digest(code), now or utcnow())
