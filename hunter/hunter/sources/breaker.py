"""Circuit breaker por fuente (SPEC §9).

- Cerrado: la fuente se usa.
- Abierto: tras N fallos seguidos se salta durante un enfriamiento que se duplica en cada reapertura.
- Semiabierto: pasado el enfriamiento se permite 1 intento; si falla, se reabre; si va bien, se cierra.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from hunter.store.repository import SourceHealth

# En estas fuentes, varias búsquedas seguidas sin resultados suelen ser un bloqueo silencioso.
SILENT_BLOCK_SOURCES = frozenset({"linkedin"})
_FAILURES = frozenset({"blocked", "timeout", "error"})

BreakerState = Literal["closed", "open", "half_open"]


@dataclass(frozen=True)
class BreakerPolicy:
    threshold: int = 3
    cooldown_h: float = 6.0
    max_cooldown_h: float = 48.0


def is_open(health: SourceHealth, now: datetime) -> bool:
    return health.open_until is not None and health.open_until > now


def state(health: SourceHealth, now: datetime, policy: BreakerPolicy) -> BreakerState:
    if is_open(health, now):
        return "open"
    if health.consecutive_failures >= policy.threshold:
        return "half_open"
    return "closed"


def after(
    health: SourceHealth, status: str, now: datetime, policy: BreakerPolicy, error: str | None = None
) -> SourceHealth:
    """Nuevo estado de salud tras una ejecución con `status`."""
    if status == "skipped_breaker_open":
        return health
    if status == "ok":
        return replace(
            health,
            consecutive_failures=0,
            consecutive_empty=0,
            times_opened=0,
            open_until=None,
            last_ok_at=now,
            last_error=None,
        )
    if status == "empty":
        health = replace(health, consecutive_empty=health.consecutive_empty + 1)
        if health.source not in SILENT_BLOCK_SOURCES or health.consecutive_empty < policy.threshold:
            return health
        status, error = "blocked", "Sin resultados en varias ejecuciones seguidas (¿bloqueo silencioso?)"
    if status not in _FAILURES:
        return health

    health = replace(health, consecutive_failures=health.consecutive_failures + 1, last_error=error or status)
    if health.consecutive_failures < policy.threshold:
        return health
    hours = min(policy.cooldown_h * (2**health.times_opened), policy.max_cooldown_h)
    return replace(health, open_until=now + timedelta(hours=hours), times_opened=health.times_opened + 1)
