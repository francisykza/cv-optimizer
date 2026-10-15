import json
from pathlib import Path

import pytest

import hunter.__main__ as cli
from hunter.config import get_settings
from tests.test_sources import FakeSource


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_raw) -> Path:
    """CLI apuntando a un directorio temporal, con fuentes falsas (sin red)."""
    monkeypatch.setattr(cli, "HUNTER_ROOT", tmp_path)
    monkeypatch.setattr(cli, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("HUNTER_DB_PATH", str(tmp_path / "data" / "hunter.db"))
    monkeypatch.setenv("HUNTER_RETENTION_DAYS", "90")
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
        cli, "build_sources", lambda rules, client, pause: [FakeSource("indeed", "ok", offers)]
    )
    yield tmp_path
    get_settings.cache_clear()


def test_full_cli_flow(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["init"])
    assert "HUNTER_TOKEN=" in (isolated / ".env").read_text(encoding="utf-8")
    assert (isolated / "data" / "profile.md").exists()

    cli.main(["run"])
    out = capsys.readouterr().out
    assert "nuevas 2" in out and "pendientes del juez 2" in out

    cli.main(["run"])  # idempotente
    assert "nuevas 0 · duplicadas 2" in capsys.readouterr().out

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
