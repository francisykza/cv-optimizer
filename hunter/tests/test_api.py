"""API local (SPEC §8) con TestClient: sin red (fuentes y LLM falsos, Jina con respx)."""

import asyncio
import time
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from hunter import services
from hunter.api.app import create_app
from hunter.config import Settings
from hunter.judge.judge import Judge, JudgeConfig, JudgeContext
from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard
from hunter.pipeline.run import Pipeline, PipelineConfig
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, utcnow
from tests.conftest import EXAMPLE_RULES, LONG_DESCRIPTION
from tests.fakes import FakeProvider, verdict_payload
from tests.test_sources import FakeSource

TOKEN = "token-local-de-pruebas-0123456789"  # noqa: S105
ORIGIN = "http://localhost:5173"
H = {"X-Hunter-Token": TOKEN}
DATA_DESCRIPTION = (
    "Equipo de datos de una cadena hotelera en Marbella busca científico de datos junior: previsión de "
    "ocupación con Python, modelos de series temporales, cuadros de mando y experimentos de precios. "
    "Mentoría semanal, formación pagada y modelo híbrido con dos días de teletrabajo."
)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        hunter_db_path=tmp_path / "hunter.db",
        hunter_token=TOKEN,
        hunter_allowed_origins=ORIGIN,
        groq_api_key="",
        hunter_retention_days=0,
        hunter_source_timeout_s=1,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def offers(make_raw) -> list:
    good = make_raw(title="Junior AI Engineer", date_posted=None)
    other = make_raw(
        title="Python Developer Junior",
        company="Otra S.L.",
        date_posted=None,
        description="Empresa de logística en Málaga busca desarrollador Python para automatizar "
        "procesos con modelos de IA: previsión de devoluciones, clasificación de incidencias y paneles "
        "internos con FastAPI.",
    )
    senior = make_raw(
        title="Senior AI Engineer",
        company="Grande S.A.",
        date_posted=None,
        description="Liderazgo técnico. " + LONG_DESCRIPTION,
    )
    short = make_raw(
        title="Junior LLM Engineer",
        company="Breve",
        description="Python y LLM.",
        date_posted=None,
        url="https://empleo.example.com/oferta/77",
    )
    return [good, other, senior, short]


@pytest.fixture
def seeded(tmp_path: Path, make_raw):
    """BD con 3 juzgadas (una con veredicto 90, otra 40, otra corta) y una descartada."""
    settings = make_settings(tmp_path)
    repo = Repository(services.open_repo(settings).conn)
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    repo.save_rules(rules)
    provider = FakeProvider(
        verdict_payload(match_score=90),
        verdict_payload(match_score=40, verdict="skip"),
        verdict_payload(match_score=70, verdict="maybe"),
        repeat_last=False,
    )
    judge = Judge(
        provider,
        repo,
        AdaptiveLimiter(tokens_per_minute=10**6),
        BudgetGuard(repo, 10**6),
        JudgeContext.from_rules(rules, "Python, LLM"),
        JudgeConfig(),
    )
    pipeline = Pipeline(repo, rules, PipelineConfig())
    asyncio.run(pipeline.run([FakeSource("indeed", "ok", offers(make_raw))], mode="full", judge=judge))
    repo.conn.close()
    with TestClient(create_app(settings)) as client:
        yield client, settings


# --- Seguridad ---------------------------------------------------------------------------------


def test_health_is_public_and_reports_config(seeded) -> None:
    client, _ = seeded
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["db_ok"] and body["token_configured"]
    assert body["groq_key_configured"] is False and body["last_run"]["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"X-Hunter-Token": "otro"}])
def test_token_is_required(seeded, headers) -> None:
    client, _ = seeded
    response = client.get("/api/v1/jobs", headers=headers)
    assert response.status_code == 401 and response.json()["error"]["code"] == "HUNTER_TOKEN_INVALID"


def test_missing_token_configuration_is_explicit(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, hunter_token=""))) as client:
        response = client.get("/api/v1/rules", headers=H)
    assert response.status_code == 503 and response.json()["error"]["code"] == "HUNTER_TOKEN_MISSING"


def test_cors_preflight_allows_frontend_and_private_network(seeded) -> None:
    client, _ = seeded
    preflight = {
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "x-hunter-token,content-type",
        "Access-Control-Request-Private-Network": "true",
    }
    ok = client.options("/api/v1/jobs/x", headers=preflight)
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert ok.headers["access-control-allow-private-network"] == "true"
    evil = client.options("/api/v1/jobs/x", headers={**preflight, "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


# --- Reglas ------------------------------------------------------------------------------------


def test_rules_roundtrip_and_validation(seeded) -> None:
    client, _ = seeded
    current = client.get("/api/v1/rules", headers=H).json()
    assert current["history"][0]["active"] is True

    bad = client.put("/api/v1/rules", headers=H, json={"rules": {"experience": {"max_years_required": "x"}}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "RULES_INVALID"
    assert bad.json()["error"]["details"][0]["path"] == "experience.max_years_required"

    rules = current["rules"]
    rules["seniority"]["exclude_title_terms"] = []  # deja de descartar "Senior"
    simulated = client.post("/api/v1/rules/simulate", headers=H, json={"rules": rules}).json()
    assert simulated["newly_kept_total"] == 1

    saved = client.put("/api/v1/rules", headers=H, json={"rules": rules}).json()
    assert saved["version"] != current["version"] and saved["now_pending_judge"] == 1


# --- Ofertas -----------------------------------------------------------------------------------


def test_ranked_view_orders_and_filters(seeded) -> None:
    client, _ = seeded
    page = client.get("/api/v1/jobs", headers=H).json()  # min_score por defecto: 55
    assert [i["verdict"]["match_score"] for i in page["items"]] == [90, 70]
    first = page["items"][0]
    assert first["judge_status"] == "ok" and first["sources"][0]["site"] == "indeed"
    assert isinstance(first["verdict"]["red_flags"], list)

    everything = client.get("/api/v1/jobs", headers=H, params={"min_score": 0}).json()
    assert everything["total"] == 3
    assert client.get("/api/v1/jobs", headers=H, params={"q": "logística"}).json()["total"] == 0
    assert client.get("/api/v1/jobs", headers=H, params={"min_score": 0, "q": "otra"}).json()["total"] == 1

    paged = client.get("/api/v1/jobs", headers=H, params={"min_score": 0, "limit": 2}).json()
    assert len(paged["items"]) == 2 and paged["next_cursor"] == "2"
    rest = client.get("/api/v1/jobs", headers=H, params={"min_score": 0, "cursor": "2"}).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None


def test_discarded_view_explains_why(seeded) -> None:
    client, _ = seeded
    items = client.get("/api/v1/jobs", headers=H, params={"view": "discarded"}).json()["items"]
    assert len(items) == 1 and items[0]["verdict"] is None
    assert items[0]["guillotine"]["rule_id"] == "SEN_TITLE"


def test_job_detail_status_and_dismiss(seeded) -> None:
    client, _ = seeded
    job_id = client.get("/api/v1/jobs", headers=H).json()["items"][0]["id"]
    detail = client.get(f"/api/v1/jobs/{job_id}", headers=H).json()
    assert detail["description"] and detail["verdict_history"][0]["match_score"] == 90
    assert client.get("/api/v1/jobs/no-existe", headers=H).status_code == 404

    patched = client.patch(f"/api/v1/jobs/{job_id}", headers=H, json={"app_status": "dismissed"}).json()
    assert patched["app_status"] == "dismissed"
    ranked = client.get("/api/v1/jobs", headers=H).json()["items"]
    assert job_id not in [i["id"] for i in ranked]  # las descartadas a mano no salen en el ranking
    assert client.patch(f"/api/v1/jobs/{job_id}", headers=H, json={"app_status": "x"}).status_code == 422


# --- Handoff al Optimizador --------------------------------------------------------------------


def _by_title(client, title: str) -> dict:
    items = client.get("/api/v1/jobs", headers=H, params={"view": "all"}).json()["items"]
    return next(i for i in items if i["title"] == title)


def test_handoff_complete_offer_is_marked_sent(seeded) -> None:
    client, _ = seeded
    job = _by_title(client, "Junior AI Engineer")
    body = client.post(f"/api/v1/jobs/{job['id']}/handoff", headers=H).json()
    assert body["complete"] and body["version"] == 1 and body["language"] == "es"
    assert body["text"].startswith("Junior AI Engineer — Acme Labs S.L. (Málaga, Andalucía, España, ")
    assert LONG_DESCRIPTION[:40] in body["text"] and body["chars"] == len(body["text"])
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["app_status"] == "sent_to_optimizer"


def test_handoff_short_offer_tries_jina_and_reports_incomplete(seeded) -> None:
    client, _ = seeded
    job = _by_title(client, "Junior LLM Engineer")
    with respx.mock(assert_all_called=True) as rx:
        jina = rx.get(url__startswith="https://r.jina.ai/").mock(return_value=httpx.Response(451))
        body = client.post(f"/api/v1/jobs/{job['id']}/handoff", headers=H).json()
    assert jina.called
    assert body["complete"] is False and body["source_url"] == "https://empleo.example.com/oferta/77"
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["app_status"] == "none"


def test_handoff_short_offer_completed_by_jina(seeded) -> None:
    client, _ = seeded
    job = _by_title(client, "Junior LLM Engineer")
    full = (
        "Oferta completa. Buscamos Junior LLM Engineer para construir agentes con Python, RAG y "
        "evaluación de modelos. Responsabilidades: diseñar prompts, integrar APIs y medir calidad. "
        "Requisitos: Python, ganas de aprender. Ofrecemos mentoría, formación y teletrabajo. "
    ) * 2
    with respx.mock(assert_all_called=True) as rx:
        rx.get(url__startswith="https://r.jina.ai/").mock(return_value=httpx.Response(200, text=full))
        body = client.post(f"/api/v1/jobs/{job['id']}/handoff", headers=H).json()
    assert body["complete"] is True and "Oferta completa" in body["text"]


# --- Runs y juez -------------------------------------------------------------------------------


def test_background_run_and_conflict(seeded, monkeypatch, make_raw) -> None:
    client, _ = seeded
    sources = [
        FakeSource(
            "indeed",
            "ok",
            [make_raw(title="Junior Data Scientist", date_posted=None, description=DATA_DESCRIPTION)],
        ),
        FakeSource("lenta", "slow"),
    ]
    monkeypatch.setattr(services, "build_sources", lambda rules, client, pause: sources)
    accepted = client.post("/api/v1/runs", headers=H, json={"mode": "ingest_only"})
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]
    assert client.post("/api/v1/runs", headers=H, json={"mode": "ingest_only"}).status_code == 409

    deadline = time.monotonic() + 10
    run = client.get(f"/api/v1/runs/{run_id}", headers=H).json()
    while run["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.1)
        run = client.get(f"/api/v1/runs/{run_id}", headers=H).json()
    assert run["status"] == "partial"  # la fuente lenta acaba en timeout; la otra funciona
    assert {s["source"]: s["status"] for s in run["sources"]} == {"indeed": "ok", "lenta": "timeout"}
    assert run["counts"]["new"] == 1, (run["counts"], run["sources"])
    assert client.get("/api/v1/runs", headers=H).json()["items"][0]["id"] == run_id
    sources_health = {s["source"]: s["state"] for s in client.get("/api/v1/sources", headers=H).json()}
    assert sources_health["lenta"] == "closed"


def test_judge_endpoints_need_a_key(seeded) -> None:
    client, _ = seeded
    run = client.post("/api/v1/runs", headers=H, json={"mode": "judge_only"})
    assert run.status_code == 503 and run.json()["error"]["code"] == "GROQ_KEY_MISSING"
    job_id = client.get("/api/v1/jobs", headers=H).json()["items"][0]["id"]
    assert client.post(f"/api/v1/jobs/{job_id}/rejudge", headers=H).status_code == 503


def test_rejudge_with_key(tmp_path: Path, make_raw, monkeypatch) -> None:
    settings = make_settings(tmp_path, groq_api_key="gsk_fake_for_tests_0123456789")
    repo = services.open_repo(settings)
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    repo.save_rules(rules)
    asyncio.run(
        Pipeline(repo, rules, PipelineConfig()).run(
            [FakeSource("indeed", "ok", [make_raw(date_posted=None)])]
        )
    )
    job_id = repo.jobs_by_stage("pending_judge", utcnow().replace(year=2000))[0].id
    repo.conn.close()
    profile = tmp_path / "profile.md"
    profile.write_text("Python, LLM", encoding="utf-8")
    monkeypatch.setattr(services, "profile_path", lambda rules: profile)
    provider = FakeProvider(verdict_payload(match_score=77))
    monkeypatch.setattr(services, "GroqProvider", lambda **kwargs: provider)
    with TestClient(create_app(settings)) as client:
        item = client.post(f"/api/v1/jobs/{job_id}/rejudge", headers=H).json()
    assert item["verdict"]["match_score"] == 77 and item["stage"] == "judged" and len(provider.requests) == 1
