"""Emparejado del navegador, cabecera Host, apagado por inactividad y botón "Apagar" (SPEC §18.2-18.3)."""

import asyncio
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hunter import pairing, services
from hunter.api import idle
from hunter.api.app import create_app
from hunter.store.repository import Repository, utcnow
from tests.test_api import ORIGIN, TOKEN, H, make_settings

# --- Códigos de un solo uso --------------------------------------------------------------------


def test_code_works_once_and_expires(repo: Repository) -> None:
    code = pairing.new_code(repo, ttl_s=120)
    assert pairing.redeem(repo, code)
    assert not pairing.redeem(repo, code)  # un solo uso

    old = pairing.new_code(repo, ttl_s=120, now=utcnow() - timedelta(minutes=5))
    assert not pairing.redeem(repo, old)  # caducado
    assert not pairing.redeem(repo, "")
    assert not pairing.redeem(repo, "x" * 500)


def test_only_the_hash_is_stored(repo: Repository) -> None:
    code = pairing.new_code(repo, ttl_s=120)
    stored = [r[0] for r in repo.conn.execute("SELECT code_sha256 FROM pairing_codes")]
    assert stored and code not in stored


@pytest.fixture
def app_client(tmp_path: Path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        yield client, settings


def test_pair_endpoint_returns_the_token_once(app_client) -> None:
    client, settings = app_client
    repo = services.open_repo(settings)
    code = pairing.new_code(repo, ttl_s=120)
    repo.conn.close()

    evil = client.post("/api/v1/pair", json={"code": code}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    ok = client.post("/api/v1/pair", json={"code": code}, headers={"Origin": ORIGIN})
    assert ok.status_code == 200 and ok.json() == {"token": TOKEN}
    again = client.post("/api/v1/pair", json={"code": code}, headers={"Origin": ORIGIN})
    assert again.status_code == 401 and again.json()["error"]["code"] == "PAIR_CODE_INVALID"


def test_unknown_host_header_is_rejected(app_client) -> None:
    """Protección frente a DNS rebinding: un dominio ajeno que apunte a 127.0.0.1 no entra."""
    client, _ = app_client
    assert client.get("/health", headers={"Host": "evil.example:8001"}).status_code == 400
    assert client.get("/health").status_code == 200


# --- Apagado -----------------------------------------------------------------------------------


def test_shutdown_needs_a_server_that_can_stop(app_client) -> None:
    client, _ = app_client
    response = client.post("/api/v1/shutdown", headers=H)
    assert response.status_code == 503 and response.json()["error"]["code"] == "SHUTDOWN_UNAVAILABLE"


def test_shutdown_button_stops_the_server(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), idle_minutes=30)
    stopped: list[bool] = []
    app.state.request_exit = lambda: stopped.append(True)
    with TestClient(app) as client:
        assert client.get("/health").json()["auto_shutdown_minutes"] == 30
        assert client.post("/api/v1/shutdown", headers=H).status_code == 202
        deadline = time.monotonic() + 3
        while not stopped and time.monotonic() < deadline:
            time.sleep(0.05)
    assert stopped == [True]


async def test_idle_watch_stops_only_when_idle_and_not_busy() -> None:
    now = [0.0]
    activity = idle.Activity(clock=lambda: now[0])
    stopped: list[bool] = []
    busy = [True]

    task = asyncio.create_task(
        idle.watch(
            activity,
            idle_s=60,
            busy=lambda: busy[0],
            request_exit=lambda: stopped.append(True),
            interval_s=0.01,
        )
    )
    now[0] = 30
    await asyncio.sleep(0.05)
    assert not stopped  # aún no han pasado 60 s
    now[0] = 120
    await asyncio.sleep(0.05)
    assert not stopped  # hay una búsqueda en marcha
    activity.touch()  # una petición reinicia la cuenta
    busy[0] = False
    await asyncio.sleep(0.05)
    assert not stopped
    now[0] = 200
    await asyncio.wait_for(task, timeout=1)
    assert stopped == [True]


def test_every_request_counts_as_activity(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        app.state.activity.last = 0.0
        client.get("/health")
        assert app.state.activity.idle_for() < 5
