"""Rate limiter en memoria con ventana deslizante, por IP.

Suficiente para una sola instancia (plan gratuito de Render). Con varias instancias
habría que moverlo a Redis.
"""

import math
import threading
import time
from collections import deque

from app.core.exceptions import RateLimitedError

_MAX_TRACKED_KEYS = 10_000


class SlidingWindowRateLimiter:
    def __init__(self, limits: list[tuple[int, float]], clock=time.monotonic) -> None:
        """`limits`: lista de (máximo de peticiones, ventana en segundos)."""
        self._limits = [(n, w) for n, w in limits if n > 0]
        self._longest_window = max((w for _, w in self._limits), default=0)
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Registra una petición o lanza RateLimitedError si se supera algún límite."""
        if not self._limits:
            return
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._longest_window:
                hits.popleft()

            for max_hits, window in self._limits:
                in_window = [t for t in hits if now - t < window]
                if len(in_window) >= max_hits:
                    retry_after = math.ceil(window - (now - in_window[0]))
                    raise RateLimitedError(retry_after_s=max(retry_after, 1))

            hits.append(now)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._evict_stale(now)

    def _evict_stale(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] >= self._longest_window]
        for k in stale:
            del self._hits[k]
