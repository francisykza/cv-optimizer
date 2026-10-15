import pytest

from hunter.pipeline.experience import required_years


@pytest.mark.parametrize(
    ("text", "years"),
    [
        # Español
        ("Requisitos:\n- 3 años de experiencia con Python", 3),
        ("Experiencia mínima de 2 años en desarrollo backend.", 2),
        ("Experiencia demostrable de al menos 4 años.", 4),
        ("Mínimo 5 años trabajando con datos.", 5),
        ("Se requieren +3 años de experiencia.", 3),
        ("Buscamos alguien con 3+ años en el puesto.", 3),
        ("3-5 años de experiencia previa.", 3),
        ("Entre 2 y 4 años de experiencia.", 2),
        ("Between 3 and 5 years of experience.", 3),
        ("Tres años de experiencia en Django.", 3),
        ("Experiencia: 2 años", 2),
        # Inglés
        ("5+ years of professional Python experience", 5),
        ("At least 4 years in backend development.", 4),
        ("Minimum of 3 years building APIs.", 3),
        ("2-4 years of experience with React.", 2),
        ("Two years of experience with AWS.", 2),
        ("Experience: 3 years", 3),
        # Varias menciones: el máximo de las obligatorias
        ("2 años de experiencia con Python. Mínimo 4 años en el sector tecnológico.", 4),
        # Sin menciones
        ("Valoramos las ganas de aprender y el trabajo en equipo.", None),
        ("", None),
    ],
)
def test_detects_required_years(text: str, years: int | None) -> None:
    assert required_years(text).years == years


@pytest.mark.parametrize(
    "text",
    [
        "Somos una empresa con 15 años de experiencia en el sector.",
        "Founded in 2005, we have 18 years of experience in fintech.",
        "Llevamos 10 años de experiencia ayudando a pymes.",
        "Valorable: 6 años de experiencia en AWS.",
        "Nice to have: 5+ years with Kubernetes.",
        "Requisitos deseables:\n- 5 años de experiencia en AWS",
        "Bonus points:\n- 7 years of experience in Go",
        "Fundada en 2023 años atrás",  # número de 4 cifras: nunca se leen sus dos últimos dígitos
    ],
)
def test_ignores_optional_and_company_mentions(text: str) -> None:
    assert required_years(text).years is None


def test_optional_section_ends_at_next_heading() -> None:
    text = "Deseable:\n- 6 años de experiencia en AWS\nRequisitos:\n- 3 años de experiencia con Python"
    assert required_years(text).years == 3


def test_returns_matched_text() -> None:
    result = required_years("Requisitos:\n- Al menos 4 años de experiencia con Python.")
    assert result.years == 4
    assert result.matched_text is not None
    assert "4 anos" in result.matched_text


def test_optional_heading_at_end_of_paragraph() -> None:
    text = "Requisitos: conocimientos de Python. Deseable:\n- 5 años de experiencia con React"
    assert required_years(text).years is None
