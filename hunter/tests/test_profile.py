"""Tu perfil desde la web (SPEC §19): el archivo, las notas que se quedan viejas, el modo `rejudge` y el
borrador a partir del CV. Sin red: proveedor LLM falso y PDFs generados en memoria."""

import asyncio
import time
from pathlib import Path

import pytest
from app.core.exceptions import UpstreamRateLimitedError
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hunter import cv_draft, profile, services
from hunter.api.app import create_app
from hunter.judge.judge import Judge, JudgeConfig, JudgeContext
from hunter.judge.limiter import AdaptiveLimiter, BudgetGuard
from hunter.judge.schema import JobVerdict, rank_score
from hunter.pipeline.prescore import prescore, profile_terms
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, StoredJob, utcnow
from tests.conftest import EXAMPLE_RULES
from tests.fakes import FakeProvider, verdict_payload
from tests.pdf_factory import make_pdf
from tests.test_api import H, make_settings, offers
from tests.test_sources import FakeSource

PROFILE_A = "## Habilidades técnicas\n- Python, LLM\n"
PROFILE_B = "## Habilidades técnicas\n- Python, FastAPI, logística\n"
PER_JOB = 1300  # tokens de cada respuesta del proveedor falso (1000 + 300)


def make_judge(repo: Repository, rules: GoldenRules, provider: FakeProvider, text: str) -> Judge:
    return Judge(
        provider,
        repo,
        AdaptiveLimiter(tokens_per_minute=10**6),
        BudgetGuard(repo, 10**6),
        JudgeContext.from_rules(rules, text),
        JudgeConfig(),
    )


@pytest.fixture
def world(tmp_path: Path, make_raw):
    """3 ofertas juzgadas con PROFILE_A (notas 90, 40 y 70) y una descartada por la guillotina."""
    settings = make_settings(tmp_path)
    repo = services.open_repo(settings)
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    repo.save_rules(rules)
    path = profile.resolve(rules, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PROFILE_A, encoding="utf-8")
    provider = FakeProvider(
        verdict_payload(match_score=90),
        verdict_payload(match_score=40, verdict="skip"),
        verdict_payload(match_score=70, verdict="maybe"),
        repeat_last=False,
    )
    pipeline = services.build_pipeline(repo, rules, settings)
    judge = make_judge(repo, rules, provider, PROFILE_A)
    asyncio.run(pipeline.run([FakeSource("indeed", "ok", offers(make_raw))], mode="full", judge=judge))
    yield repo, rules, settings, path
    repo.conn.close()


def judged(repo: Repository) -> dict[str, StoredJob]:
    return {job.title: job for job in repo.jobs_seen_since(utcnow().replace(year=2000), ("judged",))}


def note(repo: Repository, job: StoredJob) -> int:
    stored = repo.cached_verdict(job.verdict_key)
    assert stored is not None and stored.verdict_json
    return JobVerdict.model_validate_json(stored.verdict_json).match_score


# --- El archivo --------------------------------------------------------------------------------


def test_save_is_atomic_keeps_the_previous_version_and_cleans_the_text(tmp_path: Path) -> None:
    path = tmp_path / "profile.md"
    path.write_text(PROFILE_A, encoding="utf-8")
    base = profile.read(path).sha256
    saved = profile.save(path, "\n\n## Resumen  \r\nJunior\x00 en IA\r\n\n", base)
    assert path.read_bytes() == b"## Resumen\nJunior en IA\n"  # LF, sin espacios finales ni NUL
    assert saved.text == "## Resumen\nJunior en IA\n" and saved.sha256 != base
    assert profile.read_previous(path) == PROFILE_A
    # Sin temporales: solo el perfil y su versión anterior.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["profile.anterior.md", "profile.md"]

    again = profile.save(path, saved.text, saved.sha256)  # mismo texto: no toca nada
    assert again == saved and profile.read_previous(path) == PROFILE_A


def test_save_refuses_empty_too_long_or_stale_texts(tmp_path: Path) -> None:
    path = tmp_path / "profile.md"
    path.write_text(PROFILE_A, encoding="utf-8")
    base = profile.read(path).sha256
    with pytest.raises(profile.ProfileTextError, match="vacío"):
        profile.save(path, " \n\t\n", base)
    with pytest.raises(profile.ProfileTextError, match=r"4001 caracteres .* 4000"):
        profile.save(path, "x" * 4001, base)
    profile.save(path, "x" * 4000, base)  # justo lo que lee el juez

    with pytest.raises(profile.ProfileConflictError):  # el archivo cambió desde que se leyó
        profile.save(path, PROFILE_B, base)
    assert path.read_text(encoding="utf-8") == "x" * 4000 + "\n"


def test_missing_profile_reads_as_empty_and_can_be_created(tmp_path: Path) -> None:
    path = tmp_path / "nuevo" / "profile.md"
    missing = profile.read(path)
    assert (missing.text, missing.exists, missing.updated_at) == ("", False, None)
    created = profile.save(path, PROFILE_A, missing.sha256)
    assert created.exists and profile.read_previous(path) is None


def test_example_profile_terms_and_safe_path(tmp_path: Path) -> None:
    example = profile.EXAMPLE.read_text(encoding="utf-8")
    assert profile.is_example(example.replace("\n", "\r\n  ")) and not profile.is_example(PROFILE_A)
    assert profile.terms("## Skills\n- Python, SQL, python\n- Docker") == ["Python", "SQL", "Docker"]

    settings = make_settings(tmp_path)
    rules = GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))
    assert profile.resolve(rules, settings) == (settings.data_dir / "profile.md").resolve()
    assert profile.resolve(with_profile_file(rules, "data/profile.md"), settings) == (
        settings.data_dir / "profile.md"
    ).resolve()  # reglas anteriores a la SPEC 0.4.0
    for outside in (str(tmp_path / "fuera.md"), "../profile.md", "profile.txt", "../../hunter/.env"):
        with pytest.raises(profile.ProfilePathError):
            profile.resolve(with_profile_file(rules, outside), settings)


def with_profile_file(rules: GoldenRules, value: str) -> GoldenRules:
    return rules.model_copy(update={"judge": rules.judge.model_copy(update={"profile_file": value})})


# --- Notas desactualizadas, pre-score y caché -------------------------------------------------


def test_outdated_counts_notes_from_another_profile(world) -> None:
    repo, rules, settings, _ = world
    assert profile.outdated(repo, rules, settings, PROFILE_A).count == 0
    # Cambios de espacios, mayúsculas o tildes no cuentan: la caché normaliza el perfil.
    assert profile.outdated(repo, rules, settings, "## HABILIDADES TECNICAS\n-   python, llm").count == 0

    summary = profile.outdated(repo, rules, settings, PROFILE_B)
    assert (summary.count, summary.from_cache, summary.days) == (3, 0, 7)
    assert summary.est_tokens == 3 * PER_JOB  # media real de los veredictos guardados
    assert summary.est_minutes == 2  # 3 × (1300 / 6000 × 60 s + 15 s de respuesta) = 84 s
    assert summary.tokens_left_today == settings.hunter_daily_token_budget - 3 * PER_JOB

    jobs = list(judged(repo).values())
    repo.set_app_status(jobs[0].id, "dismissed")  # "No me interesa": no se gastan tokens en ella
    repo.set_app_status(jobs[1].id, "applied")  # ya inscrita: su nota ya no cambia nada
    assert profile.outdated(repo, rules, settings, PROFILE_B).count == 1

    unlimited = settings.model_copy(update={"hunter_daily_token_budget": 0})
    assert profile.outdated(repo, rules, unlimited, PROFILE_B).tokens_left_today is None


def test_rescore_uses_the_new_profile_terms(world) -> None:
    repo, rules, settings, path = world
    path.write_text(PROFILE_B, encoding="utf-8")
    pipeline = services.build_pipeline(repo, rules, settings)
    assert pipeline.rescore() > 0
    for job in judged(repo).values():
        expected = prescore(job.facts, rules, profile_terms(PROFILE_B), job.first_seen.date())
        assert job.prescore == expected
        assert job.rank_score == rank_score(note(repo, job), expected)
    assert pipeline.rescore() == 0  # ya está al día


def test_rejudge_run_updates_outdated_notes_and_keeps_them_on_failure(world) -> None:
    repo, rules, settings, path = world
    before = judged(repo)
    worst = min(before.values(), key=lambda j: j.rank_score or 0)
    repo.set_app_status(worst.id, "dismissed")
    path.write_text(PROFILE_B, encoding="utf-8")
    # La mejor colocada primero: nota nueva. La segunda: JSON roto dos veces (juicio fallido).
    provider = FakeProvider(verdict_payload(match_score=60), "no es json", "tampoco", repeat_last=False)
    judge = make_judge(repo, rules, provider, PROFILE_B)
    pipeline = services.build_pipeline(repo, rules, settings)

    run = asyncio.run(pipeline.run([], mode="rejudge", judge=judge))

    assert run.mode == "rejudge" and run.sources == [] and run.status == "ok"
    assert (run.counts.judge_queue, run.counts.judged, run.counts.judge_failed) == (2, 1, 1)
    after = judged(repo)
    best, second = sorted(
        (j for j in before.values() if j.id != worst.id), key=lambda j: j.rank_score or 0, reverse=True
    )
    assert note(repo, after[best.title]) == 60 and after[best.title].verdict_key == judge.cache_key(best)
    # El fallo no le quita la nota que tenía: sigue juzgada con el perfil anterior.
    assert after[second.title].verdict_key == second.verdict_key and note(repo, after[second.title]) == 70
    assert after[worst.title].verdict_key == worst.verdict_key  # "No me interesa": no se toca
    assert profile.outdated(repo, rules, settings, PROFILE_B).count == 1


def test_rejudge_stopped_by_quota_explains_that_notes_are_kept(world) -> None:
    repo, rules, settings, _ = world
    provider = FakeProvider(UpstreamRateLimitedError(retry_after_s=3600))
    pipeline = services.build_pipeline(repo, rules, settings)
    run = asyncio.run(pipeline.run([], mode="rejudge", judge=make_judge(repo, rules, provider, PROFILE_B)))
    assert run.budget_exhausted and run.status == "partial"
    assert "conservan su nota anterior" in (run.error or "")
    assert profile.outdated(repo, rules, settings, PROFILE_B).count == 3


def test_going_back_to_a_previous_profile_recovers_its_notes_for_free(world) -> None:
    repo, rules, settings, _ = world
    pipeline = services.build_pipeline(repo, rules, settings)
    rejudge = make_judge(repo, rules, FakeProvider(verdict_payload(match_score=55)), PROFILE_B)
    asyncio.run(pipeline.run([], mode="rejudge", judge=rejudge))
    assert sorted(note(repo, j) for j in judged(repo).values()) == [55, 55, 55]

    restored = pipeline.restore_cached(services.current_verdict_key(rules, settings, PROFILE_A))
    assert restored == 3 and sorted(note(repo, j) for j in judged(repo).values()) == [40, 70, 90]
    assert profile.outdated(repo, rules, settings, PROFILE_A).count == 0
    # Y si se vuelve otra vez al perfil B, también sale gratis.
    assert profile.outdated(repo, rules, settings, PROFILE_B).from_cache == 3


# --- API ---------------------------------------------------------------------------------------


@pytest.fixture
def client(world):
    repo, rules, settings, path = world
    with TestClient(create_app(settings)) as c:
        yield c, repo, settings, path


def test_get_profile(client) -> None:
    c, _, _, _ = client
    body = c.get("/api/v1/profile", headers=H).json()
    assert body["text"] == PROFILE_A and body["sha256"] == profile.digest(PROFILE_A)
    assert body["chars"] == len(PROFILE_A.strip()) and body["max_chars"] == 4000
    assert body["terms"] == ["Python", "LLM"]
    assert body["exists"] and not body["is_example"] and body["previous_text"] is None
    assert body["outdated"]["count"] == 0 and body["updated_at"]


def test_put_profile_saves_rescores_and_reports_outdated_notes(client) -> None:
    c, _, _, path = client
    current = c.get("/api/v1/profile", headers=H).json()
    response = c.put("/api/v1/profile", headers=H, json={"text": PROFILE_B, "base_sha256": current["sha256"]})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == PROFILE_B and body["terms"] == ["Python", "FastAPI", "logística"]
    assert body["previous_text"] == PROFILE_A
    assert body["outdated"]["count"] == 3 and body["outdated"]["est_tokens"] == 3 * PER_JOB
    assert path.read_text(encoding="utf-8") == PROFILE_B

    # Volver al anterior: las notas de ese perfil siguen en la caché y vuelven sin gastar tokens.
    back = c.put("/api/v1/profile", headers=H, json={"text": PROFILE_A, "base_sha256": body["sha256"]})
    assert back.json()["outdated"]["count"] == 0


def test_put_profile_does_not_overwrite_a_hand_edited_file(client) -> None:
    c, _, _, path = client
    stale = c.get("/api/v1/profile", headers=H).json()["sha256"]
    path.write_text("## Resumen\nEditado a mano en VS Code\n", encoding="utf-8")
    response = c.put("/api/v1/profile", headers=H, json={"text": PROFILE_B, "base_sha256": stale})
    assert response.status_code == 409 and response.json()["error"]["code"] == "PROFILE_CHANGED"
    assert "Editado a mano" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("payload", "code", "message"),
    [
        ({"text": "  \n "}, "PROFILE_INVALID", "vacío"),
        ({"text": "x" * 4001}, "PROFILE_INVALID", "4000"),
        ({"text": "x" * 20_001}, "VALIDATION_ERROR", ""),
        ({"text": PROFILE_B, "base_sha256": "no-es-un-hash"}, "VALIDATION_ERROR", ""),
    ],
)
def test_put_profile_validation(client, payload, code, message) -> None:
    c, _, _, path = client
    body = {"base_sha256": profile.digest(PROFILE_A), **payload}
    response = c.put("/api/v1/profile", headers=H, json=body)
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    assert message in response.json()["error"]["message"]
    assert path.read_text(encoding="utf-8") == PROFILE_A


def test_profile_outside_the_data_dir_is_refused(client, tmp_path: Path) -> None:
    c, repo, _, _ = client
    rules = repo.active_rules()
    secret = tmp_path / "secreto.md"
    secret.write_text("no debería leerse", encoding="utf-8")
    repo.save_rules(with_profile_file(rules, str(secret)))
    for response in (
        c.get("/api/v1/profile", headers=H),
        c.put("/api/v1/profile", headers=H, json={"text": "pisado", "base_sha256": profile.digest("")}),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROFILE_PATH_NOT_ALLOWED"
    assert secret.read_text(encoding="utf-8") == "no debería leerse"


def test_profile_routes_need_the_token(client) -> None:
    c, _, _, _ = client
    assert c.get("/api/v1/profile").status_code == 401
    assert c.put("/api/v1/profile", json={"text": "x", "base_sha256": "0" * 64}).status_code == 401
    pdf = {"Content-Type": "application/pdf"}
    assert c.post("/api/v1/profile/draft", headers=pdf, content=b"%PDF-1.4").status_code == 401


def test_rejudge_needs_a_key(client) -> None:
    c, _, _, _ = client
    response = c.post("/api/v1/runs", headers=H, json={"mode": "rejudge"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "GROQ_KEY_MISSING"


def test_rejudge_run_from_the_web(world, monkeypatch) -> None:
    repo, rules, settings, path = world
    keyed = settings.model_copy(update={"groq_api_key": SecretStr("gsk_fake_key_for_tests_0123456789")})
    provider = FakeProvider(verdict_payload(match_score=66))
    monkeypatch.setattr(services, "GroqProvider", lambda **kwargs: provider)
    with TestClient(create_app(keyed)) as c:
        sha = c.get("/api/v1/profile", headers=H).json()["sha256"]
        saved = c.put("/api/v1/profile", headers=H, json={"text": PROFILE_B, "base_sha256": sha}).json()
        assert saved["outdated"]["count"] == 3
        accepted = c.post("/api/v1/runs", headers=H, json={"mode": "rejudge"})
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        deadline = time.monotonic() + 10
        run = c.get(f"/api/v1/runs/{run_id}", headers=H).json()
        while run["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
            run = c.get(f"/api/v1/runs/{run_id}", headers=H).json()
        assert run["mode"] == "rejudge" and run["counts"]["judged"] == 3 and run["sources"] == []
        assert c.get("/api/v1/profile", headers=H).json()["outdated"]["count"] == 0
        scores = [i["verdict"]["match_score"] for i in c.get("/api/v1/jobs", headers=H).json()["items"]]
    assert scores == [66, 66, 66] and len(provider.requests) == 3


# --- Borrador desde el CV ----------------------------------------------------------------------

CV_LINES = [
    "Ana Garcia Lopez",
    "Desarrolladora junior - Malaga - ana.garcia@example.com - 600 123 456",
    "PERFIL",
    "Desarrolladora junior con base en Python y datos. Me interesa la IA aplicada",
    "y aprender en un equipo con mentoria.",
    "EXPERIENCIA PROFESIONAL",
    "Tecnica de datos - Logistica Sur S.L.",
    "03/2023 - actualidad",
    "- Automatizacion de informes con Python y SQL, que ahorro",
    "diez horas semanales al equipo.",
    "PROYECTOS",
    "- Optimizador de CV con IA (FastAPI + React): github.com/ana/cv-optimizer",
    "FORMACION Y CURSOS",
    "AI Engineering - 4Geeks Academy (2026)",
    "HABILIDADES TECNICAS",
    "Python, SQL, FastAPI, Docker, GitHub Actions, ASP.NET, Socket.io",
    "IDIOMAS",
    "Espanol nativo; ingles B2",
    "DATOS PERSONALES",
    "Fecha de nacimiento: 01/01/1995",
]


def test_draft_maps_the_cv_sections_without_contact_data() -> None:
    draft = cv_draft.build("\n".join(CV_LINES))
    text = draft.text
    assert draft.sections == [
        "Resumen",
        "Habilidades técnicas",
        "Idiomas",
        "Experiencia relevante",
        "Proyectos",
        "Formación",
    ]
    assert "## Resumen\nDesarrolladora junior con base en Python y datos. Me interesa la IA aplicada" in text
    assert "- Tecnica de datos - Logistica Sur S.L. (03/2023 - actualidad)" in text  # fecha pegada al puesto
    assert "- Automatizacion de informes con Python y SQL, que ahorro diez horas semanales al equipo." in text
    assert "- Optimizador de CV con IA (FastAPI + React)\n" in text  # sin el enlace
    assert "GitHub Actions, ASP.NET, Socket.io" in text  # tecnologías, no enlaces
    for private in ("Ana Garcia", "ana.garcia@", "600 123 456", "1995", "github.com"):
        assert private not in text
    assert profile_terms(text)[:3] == ["Python", "SQL", "FastAPI"]  # el pre-score lee las habilidades
    assert any("cabecera del CV" in w for w in draft.warnings)
    assert any("correos, teléfonos y enlaces" in w for w in draft.warnings)
    assert any("qué puesto buscas" in w for w in draft.warnings)


def test_draft_fits_in_what_the_judge_reads() -> None:
    tasks = [f"- Tarea número {i} con Python y datos " * 3 for i in range(80)]
    lines = ["PERFIL", "Junior.", "EXPERIENCIA", *tasks, "HABILIDADES", "Python, SQL"]
    draft = cv_draft.build("\n".join(lines))
    assert len(draft.text) <= cv_draft.BUDGET < profile.MAX_CHARS
    assert "## Habilidades técnicas\n- Python, SQL" in draft.text  # lo recortado es la experiencia
    assert any(w.startswith("He recortado Experiencia relevante") for w in draft.warnings)
    assert any("4000 caracteres" in w for w in draft.warnings)


def test_draft_without_recognizable_sections_keeps_the_text_to_sort_by_hand() -> None:
    draft = cv_draft.build("Ana Garcia\nana@example.com\nTrabajo con Python desde 2020\nBaloncesto")
    assert draft.text.startswith("## Mi CV (sin ordenar)\n") and "ana@example.com" not in draft.text
    assert "Trabajo con Python desde 2020" in draft.text and "No he reconocido" in draft.warnings[0]


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("EXPERIENCIA PROFESIONAL", "experience"),
        ("Experiencia", "experience"),
        ("Skills & Tools", "skills"),
        ("Habilidades:", "skills"),
        ("HABILIDADES BLANDAS", "soft"),
        ("Formación académica y cursos", "education"),
        ("Datos personales", "skip"),
        ("Formación en IA", None),  # una línea normal que empieza por un título
        ("Experiencia en atención al cliente.", None),
        ("PYTHON", None),
        ("GitHub Actions, Docker", None),
    ],
)
def test_section_titles(line: str, kind: str | None) -> None:
    assert cv_draft.section_of(line) == kind


def test_draft_endpoint_reads_the_pdf_in_memory(client) -> None:
    c, _, _, path = client
    pdf = make_pdf([CV_LINES])
    response = c.post("/api/v1/profile/draft", headers={**H, "Content-Type": "application/pdf"}, content=pdf)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"].startswith("## Resumen\n") and body["chars"] == len(body["text"].strip())
    assert "Habilidades técnicas" in body["sections"] and "ana.garcia@" not in body["text"]
    assert path.read_text(encoding="utf-8") == PROFILE_A  # un borrador no se guarda


@pytest.mark.parametrize(
    ("content_type", "content", "status", "code"),
    [
        ("application/json", b'{"cv": 1}', 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("application/pdf", b"", 400, "INVALID_PDF"),
        ("application/pdf", b"esto no es un PDF", 400, "INVALID_PDF"),
        ("application/pdf", make_pdf([[]]), 422, "PDF_NO_TEXT"),
        ("application/pdf", make_pdf([["Hola"]] * 6), 422, "TOO_MANY_PAGES"),
    ],
)
def test_draft_endpoint_errors(client, content_type, content, status, code) -> None:
    c, _, _, _ = client
    response = c.post("/api/v1/profile/draft", headers={**H, "Content-Type": content_type}, content=content)
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_draft_endpoint_refuses_large_files(client, monkeypatch) -> None:
    c, _, _, _ = client
    monkeypatch.setattr(cv_draft, "MAX_PDF_BYTES", 1024 * 1024)
    big = make_pdf([CV_LINES], padding_bytes=1024 * 1024)
    response = c.post("/api/v1/profile/draft", headers={**H, "Content-Type": "application/pdf"}, content=big)
    assert response.status_code == 413 and response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert "1 MB" in response.json()["error"]["message"]
