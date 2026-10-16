"""Apagado por inactividad (SPEC §18.3).

La API que arranca el lanzador se apaga sola tras N minutos sin peticiones, salvo que haya una
búsqueda en marcha. Mientras la web del Buscador está abierta envía un latido cada pocos minutos, así
que en la práctica se apaga un rato después de cerrarla: nadie tiene que acordarse de pararla.
"""

import asyncio
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class Activity:
    """Momento de la última petición (reloj monotónico: no le afectan los cambios de hora)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.last = clock()

    def touch(self) -> None:
        self.last = self._clock()

    def idle_for(self) -> float:
        return self._clock() - self.last


async def watch(
    activity: Activity,
    idle_s: float,
    busy: Callable[[], bool],
    request_exit: Callable[[], None],
    interval_s: float = 30.0,
) -> None:
    """Pide el apagado cuando pasan `idle_s` segundos sin peticiones y no hay ninguna búsqueda en
    marcha. Termina tras pedirlo."""
    while True:
        await asyncio.sleep(interval_s)
        if activity.idle_for() >= idle_s and not busy():
            logger.info("idle_shutdown idle_s=%.0f", activity.idle_for())
            request_exit()
            return
