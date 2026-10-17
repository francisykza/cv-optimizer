import json
from pathlib import Path

import pytest

import hunter.__main__ as cli
from hunter import services
from hunter.config import get_settings
from tests.fakes import FakeProvider, verdict_payload
from tests.test_sources import FakeSource


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_raw) -> Path:
    """CLI apuntando a un directorio temporal, con fuentes falsas (sin red)."""
    monkeypatch.setattr(cli, "HUNTER_ROOT", tmp_path)
    monkeypatch.setattr(cli, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("HUNTER_DB_PATH", str(tmp_path / "data" / "hunter.db"))
    monkeypatch.setenv("HUNTER_RETENTION_DAYS", "90")
    # Nunca la clave real de hunter/.env: sin clave por defecto; los tests del juez ponen una falsa.
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    offers = [
        make_raw(date_posted=None),
        make_raw(
            title="Python Developer",
            date_posted=None,
            description="Desarrollo de APIs con Python y FastAPI para un equipo de datos en Málaga. "
            "Integración de modelos de lenguaje, pruebas automáticas y despliegue continuo en la nube. "
            "Experiencia mínima de 2 años con Python en producción y trabajo en equipo con producto.",
        ),
    ]
    monkeypatch.setattr(
        services, "build_sources", lambda rules, client, pause: [FakeSource("indeed", "ok", offers)]
    )
    yield tmp_path
    get_settings.cache_clear()


def test_full_cli_flow(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["init"])
    assert "HUNTER_TOKEN=" in (isolated / ".env").read_text(encoding="utf-8")
    assert (isolated / "data" / "profile.md").exists()

    cli.main(["run", "--mode", "ingest_only"])
    out = capsys.readouterr().out
    assert "nuevas 2" in out and "Pendientes del juez: 2" in out and "Juez:" not in out

    cli.main(["run"])  # idempotente; sin clave, el juez no corre y se avisa
    out = capsys.readouterr().out
    assert "nuevas 0 · duplicadas 2" in out and "Sin GROQ_API_KEY" in out

    exported = isolated / "rules.json"
    cli.main(["rules", "export", str(exported)])
    data = json.loads(exported.read_text(encoding="utf-8"))
    data["experience"]["max_years_required"] = 1
    exported.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    cli.main(["simulate", str(exported)])
    out = capsys.readouterr().out
    assert "Propuesta: 1 pasan · 1 descartadas" in out and "Pide 2 años (máximo 1)" in out

    cli.main(["rules", "import", str(exported)])
    assert "1 pasan a descartadas" in capsys.readouterr().out

    cli.main(["jobs", "--stage", "discarded"])
    assert "Pide 2 años (máximo 1)" in capsys.readouterr().out

    cli.main(["sources"])
    assert "indeed" in capsys.readouterr().out


def test_invalid_rules_file_is_reported(isolated: Path) -> None:
    cli.main(["init"])
    bad = isolated / "bad.json"
    bad.write_text('{"experience": {"max_years_required": "muchos"}}', encoding="utf-8")
    with pytest.raises(SystemExit, match="experience.max_years_required"):
        cli.main(["rules", "import", str(bad)])


def test_run_without_init_explains_what_to_do(isolated: Path) -> None:
    with pytest.raises(SystemExit, match="hunter init"):
        cli.main(["run"])


def test_judge_commands(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake_key_for_tests_0123456789")
    get_settings.cache_clear()
    provider = FakeProvider(
        verdict_payload(red_flags=[{"text": "Cita inventada", "evidence": "salario de 90.000 euros al año"}])
    )
    monkeypatch.setattr(services, "GroqProvider", lambda **kwargs: provider)
    cli.main(["init"])
    cli.main(["run"])
    out = capsys.readouterr().out
    assert "Juez: 2 juzgadas (0 desde caché)" in out and "Pendientes del juez: 0" in out

    cli.main(["jobs", "--stage", "judged"])
    out = capsys.readouterr().out
    assert "[ 82] APLICAR" in out and "Cita inventada" in out
    job_id = out.split("id ")[1][:8]

    cli.main(["show", job_id])
    out = capsys.readouterr().out
    assert "82/100 · APLICAR" in out and "sin cita verificable" in out and "Stack real: Python" in out

    calls = len(provider.requests)
    cli.main(["rejudge", job_id])
    assert len(provider.requests) == calls + 1 and "ok · 1300 tokens" in capsys.readouterr().out

    with pytest.raises(SystemExit, match="No hay ninguna oferta"):
        cli.main(["show", "zzzz"])


def test_judge_only_requires_a_key(isolated: Path) -> None:
    cli.main(["init"])
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        cli.main(["run", "--mode", "judge_only"])
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        cli.main(["run", "--mode", "rejudge"])


def test_rejudge_after_changing_the_profile(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake_key_for_tests_0123456789")
    get_settings.cache_clear()
    provider = FakeProvider(verdict_payload())
    monkeypatch.setattr(services, "GroqProvider", lambda **kwargs: provider)
    cli.main(["init"])
    cli.main(["run"])
    assert len(provider.requests) == 2
    capsys.readouterr()

    cli.main(["run", "--mode", "rejudge"])  # el perfil no ha cambiado: nada que volver a juzgar
    out = capsys.readouterr().out
    assert "Juez: 0 juzgadas" in out and "Leídas" not in out and len(provider.requests) == 2

    profile_md = isolated / "data" / "profile.md"
    profile_md.write_text(profile_md.read_text(encoding="utf-8") + "\n- También Rust\n", encoding="utf-8")
    cli.main(["run", "--mode", "rejudge"])
    assert "Juez: 2 juzgadas (0 desde caché)" in capsys.readouterr().out and len(provider.requests) == 4
