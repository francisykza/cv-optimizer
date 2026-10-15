from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from hunter.models import RawJob
from hunter.rules.schema import GoldenRules
from hunter.store.db import connect
from hunter.store.repository import Repository

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_RULES = Path(__file__).parent.parent / "rules.example.json"

LONG_DESCRIPTION = (
    "Buscamos una persona junior para nuestro equipo de inteligencia artificial en Málaga. "
    "Trabajarás con Python y FastAPI construyendo servicios con modelos de lenguaje (LLM) y RAG. "
    "Formarás parte de un equipo pequeño con mentoría de perfiles senior y revisiones de código. "
    "Ofrecemos horario flexible, formación continua y un plan de carrera claro desde el primer día. "
    "Requisitos: conocimientos de Python, ganas de aprender y buen nivel de inglés técnico."
)


@pytest.fixture
def repo() -> Repository:
    return Repository(connect(":memory:"))


@pytest.fixture
def rules() -> GoldenRules:
    return GoldenRules.model_validate_json(EXAMPLE_RULES.read_text(encoding="utf-8"))


@pytest.fixture
def make_raw() -> Callable[..., RawJob]:
    counter = iter(range(1, 10_000))

    def factory(**overrides: object) -> RawJob:
        n = next(counter)
        data: dict[str, object] = {
            "site": "indeed",
            "site_job_id": f"id-{n}",
            "url": f"https://es.indeed.com/viewjob?jk=abc{n:06d}",
            "title": "Junior AI Engineer",
            "company": "Acme Labs S.L.",
            "location": "Málaga, Andalucía, España",
            "description": LONG_DESCRIPTION,
            "date_posted": date(2026, 10, 14),
        }
        data.update(overrides)
        return RawJob.model_validate(data)

    return factory
