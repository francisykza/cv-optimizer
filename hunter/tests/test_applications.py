"""Candidaturas (SPEC §18.4): repositorio, resumen, CSV y API."""

import asyncio
import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hunter import applications, services
from hunter.api.app import create_app
from hunter.models import ApplicationEvent, ApplicationIn, ApplicationRecord
from hunter.pipeline.run import Pipeline, PipelineConfig
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, utcnow
from tests.conftest import EXAMPLE_RULES
from tests.test_api import H, make_settings
from tests.test_sources import FakeSource

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def _app(**overrides) -> ApplicationIn:
    data = {"id": "cand-0001", "company": "Acme Labs", "title": "Junior AI Engineer", "source": "optimizer"}
    data.update(overrides)
    return ApplicationIn.model_validate(data)


def _record(
    status: str = "applied", score: int | None = 80, days_ago: int = 1, history=()
) -> ApplicationRecord:
    applied = NOW - timedelta(days=days_ago)
    events = [ApplicationEvent(status="applied", at=applied)]
    events += [ApplicationEvent(status=s, at=applied + timedelta(days=1)) for s in history]
    return ApplicationRecord(
        id=f"r-{status}-{score}-{days_ago}",
        job_id=None,
        company="Acme",
        title="Dev",
        url=None,
        location="",
        source="manual",
        status=status,
        applied_at=applied,
        status_changed_at=events[-1].at,
        ats_score_before=None,
        ats_score_after=score,
        judge_score=None,
        notes="",
        events=events,
    )


# --- Repositorio -------------------------------------------------------------------------------


def _job_id(repo: Repository, make_raw) -> str:
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    asyncio.run(Pipeline(repo, rules, PipelineConfig()).run([FakeSource("indeed", "ok", [make_raw()])]))
    return repo.jobs_by_stage("pending_judge", utcnow() - timedelta(days=1))[0].id


def test_create_is_idempotent_and_marks_the_job_applied(repo: Repository, make_raw) -> None:
    job_id = _job_id(repo, make_raw)
    assert repo.create_application(_app(job_id=job_id, ats_score_after=86, offer_text="Oferta"), NOW)
    assert not repo.create_application(_app(job_id=job_id, company="Otra"), NOW)  # mismo id: no cambia

    [listed] = repo.applications()
    assert (listed.company, listed.ats_score_after, listed.status) == ("Acme Labs", 86, "applied")
    assert listed.has_offer_text and not listed.has_cv and listed.offer_text is None  # listado ligero
    assert [e.status for e in listed.events] == ["applied"]
    assert repo.get_application("cand-0001").offer_text == "Oferta"
    assert repo.get_job(job_id).app_status == "applied"


def test_status_changes_leave_history_and_delete_reverts_the_job(repo: Repository, make_raw) -> None:
    job_id = _job_id(repo, make_raw)
    repo.create_application(_app(job_id=job_id), NOW)
    later = NOW + timedelta(days=5)
    assert repo.update_application("cand-0001", {"status": "interview", "notes": "Llamada"}, later)
    assert repo.update_application("cand-0001", {"notes": "Llamada el lunes"}, later + timedelta(hours=1))
    record = repo.get_application("cand-0001")
    assert [e.status for e in record.events] == ["applied", "interview"]
    assert record.status_changed_at == later and record.notes == "Llamada el lunes"
    assert not repo.update_application("no-existe", {"status": "offer"}, later)

    assert repo.delete_application("cand-0001") and repo.get_application("cand-0001") is None
    assert repo.get_job(job_id).app_status == "none"
    assert not repo.delete_application("cand-0001")


def test_past_application_date_is_kept(repo: Repository) -> None:
    applied = NOW - timedelta(days=30)
    repo.create_application(_app(applied_at=applied, source="manual"), NOW)
    record = repo.get_application("cand-0001")
    assert record.applied_at == applied == record.status_changed_at


# --- Resumen y CSV -----------------------------------------------------------------------------


def test_stats_count_responses_by_compatibility_band() -> None:
    records = [
        _record("applied", 85, days_ago=2),
        _record("rejected", 90, days_ago=10, history=["interview", "rejected"]),
        _record("interview", 65, days_ago=12, history=["interview"]),
        _record("applied", 40, days_ago=30),  # 30 días sin noticias: "¿sin respuesta?"
        _record("no_response", None, days_ago=40, history=["no_response"]),
    ]
    stats = applications.compute_stats(records, NOW)
    assert (stats.total, stats.last_7_days, stats.awaiting, stats.stale) == (5, 1, 2, 1)
    assert (stats.responded, stats.interviews, stats.offers) == (2, 2, 0)
    assert stats.avg_ats_after == 70  # (85 + 90 + 65 + 40) / 4
    bands = {b.label: (b.total, b.responded) for b in stats.by_band}
    assert bands == {
        "80 % o más": (2, 1),
        "Entre 60 y 79 %": (1, 1),
        "Menos de 60 %": (1, 0),
        applications.WITHOUT_SCORE: (1, 0),
    }
    assert applications.compute_stats([], NOW).avg_ats_after is None


def test_select_filters_by_status_and_text() -> None:
    records = [_record("applied", 85), _record("interview", 70, history=["interview"])]
    assert len(applications.select(records, status="interview")) == 1
    assert len(applications.select(records, q="ACME")) == 2
    assert applications.select(records, q="nada") == []


def test_csv_opens_in_spanish_excel_and_neutralises_formulas() -> None:
    record = _record("interview", 86, history=["interview"]).model_copy(
        update={
            "company": '=HYPERLINK("http://x")',
            "notes": "Llamar; el lunes",
            "url": "https://x.example/1",
        }
    )
    data = applications.to_csv([record])
    assert data.startswith(b"\xef\xbb\xbf")  # BOM: Excel lee bien las tildes
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][0] == "Fecha" and rows[0][5] == "Compatibilidad del CV enviado (%)"
    assert rows[1][1].startswith("'=")  # una celda con = no se ejecuta como fórmula
    assert rows[1][4] == "Entrevista" and rows[1][5] == "86" and rows[1][9] == "Llamar; el lunes"


# --- API ---------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path):
    settings = make_settings(tmp_path)
    services.open_repo(settings).conn.close()
    with TestClient(create_app(settings)) as c:
        yield c


def test_api_create_list_update_and_delete(client: TestClient) -> None:
    body = {
        "id": "a1b2c3d4e5",
        "company": "Acme",
        "title": "Junior AI Engineer",
        "url": "https://www.linkedin.com/jobs/view/1",
        "source": "optimizer",
        "ats_score_before": 54,
        "ats_score_after": 86,
        "offer_text": "Buscamos...",
        "cv_markdown": "# Francisco",
        "job_id": "no-existe",  # la oferta ya no está en el Buscador: se guarda sin enlace
    }
    created = client.post("/api/v1/applications", headers=H, json=body)
    assert created.status_code == 201
    assert created.json()["job_id"] is None and created.json()["cv_markdown"] == "# Francisco"
    again = client.post("/api/v1/applications", headers=H, json=body)
    assert again.status_code == 200  # reenvío desde la cola del navegador

    page = client.get("/api/v1/applications", headers=H).json()
    assert page["total"] == 1 and page["stats"]["avg_ats_after"] == 86
    item = page["items"][0]
    assert item["has_cv"] and "cv_markdown" not in item and item["stale"] is False

    patched = client.patch(
        "/api/v1/applications/a1b2c3d4e5", headers=H, json={"status": "interview", "url": ""}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "interview" and patched.json()["url"] is None
    assert [e["status"] for e in patched.json()["events"]] == ["applied", "interview"]
    assert client.patch("/api/v1/applications/a1b2c3d4e5", headers=H, json={"status": "x"}).status_code == 422
    assert client.get("/api/v1/applications", headers=H, params={"status": "applied"}).json()["total"] == 0

    detail = client.get("/api/v1/applications/a1b2c3d4e5", headers=H).json()
    assert detail["offer_text"] == "Buscamos..."

    exported = client.get("/api/v1/applications.csv", headers=H)
    assert exported.headers["content-type"].startswith("text/csv")
    assert "candidaturas.csv" in exported.headers["content-disposition"]

    assert client.delete("/api/v1/applications/a1b2c3d4e5", headers=H).status_code == 204
    missing = client.get("/api/v1/applications/a1b2c3d4e5", headers=H)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "APPLICATION_NOT_FOUND"


def test_api_validates_and_requires_the_token(client: TestClient) -> None:
    assert client.get("/api/v1/applications").status_code == 401
    bad = client.post("/api/v1/applications", headers=H, json={"id": "corto", "company": "A", "title": "B"})
    assert bad.status_code == 422
    ftp = {"id": "a1b2c3d4e5", "company": "A", "title": "B", "url": "ftp://x"}
    assert client.post("/api/v1/applications", headers=H, json=ftp).status_code == 422
    score = {"id": "a1b2c3d4e5", "company": "A", "title": "B", "ats_score_after": 140}
    assert client.post("/api/v1/applications", headers=H, json=score).status_code == 422
