"""Lanzador del acceso directo (SPEC §18.1) y carpeta de datos fuera de OneDrive."""

from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hunter import launcher, pairing, services
from hunter.config import HUNTER_ROOT, Settings, default_data_dir
from hunter.models import Run
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, utcnow
from tests.conftest import EXAMPLE_RULES
from tests.test_api import TOKEN, make_settings

HEALTH = {
    "status": "ok",
    "version": "0.4.0",
    "db_ok": True,
    "groq_key_configured": False,
    "token_configured": True,
}


def _run(repo: Repository, *, hours_ago: float, mode: str = "full", status: str = "ok") -> None:
    started = utcnow() - timedelta(hours=hours_ago)
    run = Run(
        id=f"run-{hours_ago}-{mode}",
        trigger="api",
        mode=mode,
        status="running",
        started_at=started,
        rules_version="x",
    )
    repo.create_run(run)
    if status != "running":
        repo.finish_run(
            run.model_copy(update={"status": status, "finished_at": started + timedelta(minutes=5)})
        )


# --- ¿Toca buscar? -----------------------------------------------------------------------------


def test_search_is_due_when_never_searched_or_old(repo: Repository) -> None:
    now = utcnow()
    assert launcher.search_is_due(repo, hours=12, now=now)
    _run(repo, hours_ago=20)
    assert launcher.search_is_due(repo, hours=12, now=now)
    _run(repo, hours_ago=2, mode="judge_only")  # solo juez: no cuenta como búsqueda en los portales
    assert launcher.search_is_due(repo, hours=12, now=now)
    _run(repo, hours_ago=3)
    assert not launcher.search_is_due(repo, hours=12, now=now)
    assert not launcher.search_is_due(repo, hours=0, now=now + timedelta(days=9))  # desactivado


def test_search_is_not_due_while_one_is_running(repo: Repository) -> None:
    _run(repo, hours_ago=0, status="running")
    assert not launcher.search_is_due(repo, hours=12, now=utcnow())


def test_orphan_run_does_not_block_the_next_search(repo: Repository) -> None:
    _run(repo, hours_ago=30)
    _run(repo, hours_ago=5, status="running")  # sin latido desde hace 5 h: el PC se apagó
    assert launcher.search_is_due(repo, hours=12, now=utcnow())


# --- Doble clic --------------------------------------------------------------------------------


def _mock_client(alive_after: int = 0, health: dict | None = None, calls: list | None = None) -> httpx.Client:
    seen = {"health": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.method, request.url.path, request.headers.get("x-hunter-token")))
        if request.url.path == "/health":
            seen["health"] += 1
            if seen["health"] <= alive_after:
                raise httpx.ConnectError("apagada")
            return httpx.Response(200, json=health or HEALTH)
        if request.url.path == "/api/v1/runs":
            return httpx.Response(202, json={"run_id": "r1", "status": "running"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    settings = make_settings(tmp_path, hunter_web_url="https://cv.example/", hunter_autorun_hours=12)
    repo = services.open_repo(settings)
    repo.save_rules(GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8")))
    repo.conn.close()
    return settings


def test_open_with_api_running_pairs_and_starts_a_due_search(settings: Settings) -> None:
    calls: list = []
    opened: list[str] = []
    spawned: list[Settings] = []
    url = launcher.open_buscador(
        settings,
        client=_mock_client(calls=calls),
        browser=lambda u: opened.append(u) or True,
        spawn=spawned.append,
    )
    assert spawned == [] and opened == [url]
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://cv.example/"
    assert parts.query == "hunter=1" and parts.fragment.startswith("/buscar?pair=")
    code = parse_qs(parts.fragment.split("?", 1)[1])["pair"][0]
    repo = services.open_repo(settings)
    assert pairing.redeem(repo, code)  # el código abre la sesión una vez
    repo.conn.close()
    assert ("POST", "/api/v1/runs", TOKEN) in calls  # nunca se había buscado


def test_open_starts_the_api_when_it_is_off(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(launcher, "POLL_EVERY_S", 0)
    spawned: list[Settings] = []
    launcher.open_buscador(
        settings,
        search=False,
        client=_mock_client(alive_after=3),
        browser=lambda u: True,
        spawn=spawned.append,
    )
    assert spawned == [settings]


def test_open_explains_what_went_wrong(settings: Settings, tmp_path: Path) -> None:
    other_program = _mock_client(health={"hello": "world"})
    with pytest.raises(launcher.LauncherError, match="otro programa"):
        launcher.open_buscador(settings, client=other_program, browser=lambda u: True, spawn=lambda s: None)

    no_token = make_settings(tmp_path, hunter_token="")
    with pytest.raises(launcher.LauncherError, match="HUNTER_TOKEN"):
        launcher.open_buscador(no_token, client=_mock_client(), browser=lambda u: True)

    with pytest.raises(launcher.LauncherError, match="navegador"):
        launcher.open_buscador(settings, search=False, client=_mock_client(), browser=lambda u: False)


def test_wait_until_alive_gives_up_with_a_hint(tmp_path: Path) -> None:
    clock = iter(range(0, 1000, 10))
    with pytest.raises(launcher.LauncherError, match="hunter.log"):
        launcher.wait_until_alive(
            "http://127.0.0.1:8001",
            _mock_client(alive_after=10**6),
            tmp_path / "logs",
            timeout_s=30,
            sleep=lambda s: None,
            clock=lambda: next(clock),
        )


def test_server_command_prefers_pythonw(tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    python.touch()
    settings = make_settings(tmp_path, hunter_idle_minutes=25)
    assert launcher.server_command(settings, str(python)) == [
        str(python),
        "-m",
        "hunter",
        "serve",
        "--idle",
        "25",
    ]
    (tmp_path / "pythonw.exe").touch()
    assert launcher.server_command(settings, str(python))[0] == str(tmp_path / "pythonw.exe")


# --- Carpeta de datos --------------------------------------------------------------------------


def test_default_data_dir_is_outside_the_repository_on_windows() -> None:
    local = {"LOCALAPPDATA": "C:/Users/ana/AppData/Local"}
    assert default_data_dir(local, "nt") == Path("C:/Users/ana/AppData/Local") / "CV-Optimizer" / "hunter"
    assert default_data_dir({}, "nt") == HUNTER_ROOT / "data"
    assert default_data_dir(local, "posix") == HUNTER_ROOT / "data"


def test_data_dir_precedence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HUNTER_DATA_DIR", raising=False)
    explicit = Settings(
        _env_file=None, hunter_data_dir=tmp_path / "a", hunter_db_path=tmp_path / "b" / "x.db"
    )
    assert explicit.data_dir == tmp_path / "a" and explicit.db_path == tmp_path / "b" / "x.db"
    beside_db = Settings(_env_file=None, hunter_db_path=tmp_path / "b" / "x.db")
    assert beside_db.data_dir == tmp_path / "b"
    default = Settings(_env_file=None)
    assert default.db_path == default.data_dir / "hunter.db"


@pytest.mark.parametrize("configured", ["data/profile.md", "profile.md"])
def test_profile_lives_in_the_data_dir(configured: str, tmp_path: Path) -> None:
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    rules.judge.profile_file = configured  # "data/..." es como lo guardaban las reglas antiguas
    settings = Settings(_env_file=None, hunter_data_dir=tmp_path)
    assert services.profile_path(rules, settings) == tmp_path / "profile.md"
    rules.judge.profile_file = str(tmp_path / "otro.md")
    assert services.profile_path(rules, settings) == tmp_path / "otro.md"


def test_two_processes_opening_a_new_database_do_not_collide(tmp_path: Path) -> None:
    from hunter.store.db import connect

    first = connect(tmp_path / "hunter.db")
    second = connect(tmp_path / "hunter.db")  # ya migrada: no repite nada
    versions = {c.execute("PRAGMA user_version").fetchone()[0] for c in (first, second)}
    assert versions == {4}
    first.close()
    second.close()
