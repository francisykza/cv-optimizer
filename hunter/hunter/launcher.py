"""Lanzador del acceso directo del escritorio (SPEC §18.1): `python -m hunter open`.

Un doble clic y el Buscador está listo:
1. Si la API local no responde, la arranca en segundo plano, sin ventana, con apagado por inactividad.
2. Si la última búsqueda terminó hace más de `HUNTER_AUTORUN_HOURS`, lanza otra.
3. Abre la web en el Buscador con un código de un solo uso para que se conecte sola.

El acceso directo usa pythonw.exe (sin consola): los errores se muestran en una ventana de aviso.
"""

import os
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx

from hunter import pairing, services
from hunter.config import HUNTER_ROOT, Settings
from hunter.pipeline.run import STALE_RUN_AFTER
from hunter.store.repository import Repository, utcnow

START_TIMEOUT_S = 40.0  # el primer arranque importa FastAPI y el backend: unos segundos
POLL_EVERY_S = 0.4


class LauncherError(Exception):
    """Fallo que el usuario tiene que ver (con pythonw no hay consola)."""


def api_base(settings: Settings) -> str:
    return f"http://{settings.hunter_host}:{settings.hunter_port}"


def api_alive(base: str, client: httpx.Client) -> bool:
    """True si responde la API del hunter. Si el puerto lo ocupa otro programa, error explícito."""
    try:
        response = client.get(f"{base}/health", timeout=1.5)
    except httpx.HTTPError:
        return False
    try:
        is_hunter = response.status_code == 200 and "token_configured" in response.json()
    except ValueError:
        is_hunter = False
    if not is_hunter:
        raise LauncherError(
            f"El puerto de la API local ({base}) lo está usando otro programa. "
            "Elige otro con HUNTER_PORT en hunter/.env."
        )
    return True


def server_command(settings: Settings, executable: str = sys.executable) -> list[str]:
    """pythonw.exe si existe (sin ventana de consola), si no el mismo intérprete."""
    exe = Path(executable)
    windowless = exe.with_name("pythonw.exe")
    python = windowless if windowless.exists() else exe
    return [str(python), "-m", "hunter", "serve", "--idle", str(settings.hunter_idle_minutes)]


def spawn_server(settings: Settings) -> None:
    """Arranca la API como proceso independiente: sigue viva cuando el lanzador termina."""
    options: dict[str, object] = {
        "cwd": HUNTER_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    subprocess.Popen(server_command(settings), **options)  # noqa: S603 (comando fijo, sin shell)


def wait_until_alive(
    base: str,
    client: httpx.Client,
    log_dir: Path,
    timeout_s: float = START_TIMEOUT_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout_s
    while clock() < deadline:
        if api_alive(base, client):
            return
        sleep(POLL_EVERY_S)
    raise LauncherError(
        f"La API local no ha arrancado en {timeout_s:.0f} s. Los detalles están en {log_dir / 'hunter.log'}."
    )


def search_is_due(repo: Repository, hours: float, now: datetime) -> bool:
    """Toca buscar si nunca se ha hecho o si la última búsqueda en los portales terminó hace más de
    `hours` horas. Si hay una en marcha (con latido reciente), no; una huérfana no cuenta."""
    if hours <= 0 or repo.live_run(STALE_RUN_AFTER):
        return False
    for run in repo.recent_runs(10):
        if run.mode in ("full", "ingest_only") and run.finished_at is not None:
            return now - run.finished_at > timedelta(hours=hours)
    return True


def start_search(base: str, client: httpx.Client, token: str) -> bool:
    """Lanza una búsqueda completa en la API. False si ya había otra en marcha o no se pudo."""
    try:
        response = client.post(
            f"{base}/api/v1/runs", json={"mode": "full"}, headers={"X-Hunter-Token": token}, timeout=10
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 202


def buscador_url(settings: Settings, code: str) -> str:
    return f"{settings.web_url}/?hunter=1#/buscar?pair={quote(code)}"


def open_buscador(
    settings: Settings,
    *,
    search: bool = True,
    client: httpx.Client | None = None,
    browser: Callable[[str], bool] = webbrowser.open,
    spawn: Callable[[Settings], None] = spawn_server,
) -> str:
    """Todo lo que hace el doble clic. Devuelve la URL abierta (sin el código no sirve de nada)."""
    token = settings.hunter_token.get_secret_value() if settings.hunter_token else ""
    if not token:
        raise LauncherError("Falta HUNTER_TOKEN en hunter/.env. Ejecuta antes: python -m hunter init")
    base = api_base(settings)
    http = client or httpx.Client()
    try:
        if not api_alive(base, http):
            spawn(settings)
            wait_until_alive(base, http, settings.data_dir / "logs")
        repo = services.open_repo(settings)
        try:
            code = pairing.new_code(repo, settings.hunter_pairing_ttl_s)
            due = search and search_is_due(repo, settings.hunter_autorun_hours, utcnow())
        finally:
            repo.conn.close()
        if due:
            start_search(base, http, token)
    finally:
        if client is None:
            http.close()
    url = buscador_url(settings, code)
    if not browser(url):
        raise LauncherError(f"No he podido abrir el navegador. Abre esta dirección a mano:\n{url}")
    return url


def alert(message: str) -> None:
    """Con consola, por stderr. Sin consola (pythonw.exe, el acceso directo), en una ventana."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)
        return
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Buscador de empleo", 0x10)  # MB_ICONERROR
