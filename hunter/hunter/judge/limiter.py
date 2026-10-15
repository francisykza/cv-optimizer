"""Protección de rate limits del free tier de Groq y presupuesto diario (SPEC §7.4).

- `AdaptiveLimiter`: antes de cada llamada estima su coste y espera si no cabe. Combina una
  ventana local de 60 s (tokens por minuto) con lo que Groq dice en sus cabeceras
  `x-ratelimit-*`, que manda cuando está disponible. Así el 429 es la excepción.
- `BudgetGuard`: tope de tokens al día (día local del equipo), guardado en SQLite.

Si hay que esperar más de `max_wait_s` (cuota diaria agotada), se lanza `QuotaExhaustedError` y el
juez se detiene limpio: lo pendiente se retoma en la siguiente ejecución.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import date, datetime

from app.services.llm.base import RateLimitInfo

from hunter.store.repository import Repository

WINDOW_S = 60.0


class QuotaExhaustedError(Exception):
    def __init__(self, reason: str, wait_s: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.wait_s = wait_s


def estimate_tokens(text: str) -> int:
    """~3,5 caracteres por token en español/inglés con mucho vocabulario técnico."""
    return int(len(text) / 3.5) + 1


class AdaptiveLimiter:
    def __init__(
        self,
        tokens_per_minute: int = 6000,
        max_wait_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.tokens_per_minute = tokens_per_minute
        self.max_wait_s = max_wait_s
        self._clock = clock
        self._sleep = sleep
        self._events: deque[list[float]] = deque()  # [instante, tokens]
        self._remaining_tokens: int | None = None
        self._tokens_reset_at = 0.0
        self._remaining_requests: int | None = None
        self._requests_reset_at = 0.0
        self.waited_s = 0.0

    def _used_in_window(self, now: float) -> float:
        while self._events and now - self._events[0][0] >= WINDOW_S:
            self._events.popleft()
        return sum(tokens for _, tokens in self._events)

    def wait_needed(self, cost: int) -> float:
        now = self._clock()
        if self._remaining_requests == 0 and self._requests_reset_at > now:
            return self._requests_reset_at - now
        if (
            self._remaining_tokens is not None
            and self._tokens_reset_at > now
            and cost > self._remaining_tokens
        ):
            return self._tokens_reset_at - now
        used = self._used_in_window(now)
        if self._events and used + cost > self.tokens_per_minute:
            # Esperar a que caduquen las llamadas más antiguas hasta que quepa esta.
            excess = used + cost - self.tokens_per_minute
            freed = 0.0
            for started, tokens in self._events:
                freed += tokens
                if freed >= excess:
                    return max(0.0, started + WINDOW_S - now)
        return 0.0

    async def acquire(self, cost: int) -> None:
        while True:
            wait = self.wait_needed(cost)
            if wait <= 0:
                break
            if wait > self.max_wait_s:
                raise QuotaExhaustedError("rate_limit", wait)
            self.waited_s += wait
            await self._sleep(wait + 0.05)
        self._events.append([self._clock(), float(cost)])

    def observe(self, info: RateLimitInfo | None, used_tokens: int | None = None) -> None:
        """Corrige la estimación con el consumo real y adopta las cabeceras del proveedor."""
        now = self._clock()
        if used_tokens is not None and self._events:
            self._events[-1][1] = float(used_tokens)
        if info is None:
            return
        if info.remaining_tokens is not None:
            self._remaining_tokens = info.remaining_tokens
            self._tokens_reset_at = now + (info.reset_tokens_s or WINDOW_S)
        if info.limit_tokens:
            self.tokens_per_minute = min(self.tokens_per_minute, info.limit_tokens)
        if info.remaining_requests is not None:
            self._remaining_requests = info.remaining_requests
            self._requests_reset_at = now + (info.reset_requests_s or 0.0)

    def observe_rate_limited(self, retry_after_s: float | None) -> None:
        """Groq devolvió 429 incluso tras los reintentos: no volver a llamar hasta el reset."""
        now = self._clock()
        self._remaining_tokens = 0
        self._tokens_reset_at = now + (retry_after_s if retry_after_s is not None else WINDOW_S)


def local_today() -> date:
    # Día local del equipo (en España). Sin zoneinfo: Windows no trae la base de datos de zonas.
    return datetime.now().astimezone().date()


class BudgetGuard:
    def __init__(self, repo: Repository, daily_budget: int, today: Callable[[], date] = local_today) -> None:
        self.repo = repo
        self.daily_budget = daily_budget
        self._today = today

    def used(self) -> int:
        return self.repo.tokens_used(self._today())

    def remaining(self) -> int:
        return max(0, self.daily_budget - self.used())

    def check(self, cost: int) -> None:
        if self.daily_budget > 0 and self.used() + cost > self.daily_budget:
            raise QuotaExhaustedError("daily_budget")

    def add(self, tokens: int) -> None:
        self.repo.add_tokens(self._today(), tokens)
