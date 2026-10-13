"""El validador debe detectar lo inventado SIN marcar reformulaciones legítimas."""

import pytest

from app.services.output_validator import OutputValidator, SourceIndex, detect_language
from tests.pdf_factory import SAMPLE_CV_LINES

SOURCE_CV = "\n".join(SAMPLE_CV_LINES)
KEYWORDS = ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Terraform", "APIs REST"]

FAITHFUL_CV = """# Ana García López
Desarrolladora Backend · Madrid · ana.garcia@example.com

## Resumen profesional
Desarrolladora backend especializada en APIs REST con **FastAPI** y **PostgreSQL**, y en el
despliegue de servicios con Docker y GitHub Actions.

## Experiencia
### Desarrolladora Python — Acme Software SL
*2021 – Actualidad*
- Diseño y desarrollo de APIs REST con FastAPI y PostgreSQL.
- Despliegue de servicios con Docker y GitHub Actions.
- Reducción del tiempo de respuesta de la API en un 30%.

### Programadora junior — Beta Consulting
*2019 – 2021*
- Mantenimiento de aplicaciones Django.

## Formación
**Grado en Ingeniería Informática** — Universidad Complutense de Madrid (2015 – 2019)

## Habilidades
- **Lenguajes y frameworks:** Python, FastAPI, Django
- **Bases de datos:** PostgreSQL
- **DevOps:** Docker, Git, GitHub Actions
- **Idiomas:** Inglés (B2)
"""


def validate(markdown: str, keywords=KEYWORDS):
    return OutputValidator().validate(markdown, SOURCE_CV, keywords)


def codes(report) -> list[tuple[str, str]]:
    return [(w.code, w.term) for w in report.warnings]


def test_faithful_rewrite_has_no_warnings():
    report = validate(FAITHFUL_CV)
    assert report.warnings == []
    assert report.ungrounded_count == 0


def test_detects_invented_year():
    report = validate(FAITHFUL_CV.replace("*2019 – 2021*", "*2017 – 2021*"))
    assert ("UNGROUNDED_DATE", "2017") in codes(report)


@pytest.mark.parametrize(
    ("original", "invented", "term"),
    [
        ("en un 30%", "en un 45%", "45"),
        ("Mantenimiento de aplicaciones Django.", "Mantenimiento de 12 aplicaciones Django.", "12"),
        ("## Resumen profesional\n", "## Resumen profesional\nMás de 5 años de experiencia. ", "5"),
        # Regresión (visto en producción): el "2" de "inglés B2" no respalda "2 años".
        ("## Resumen profesional\n", "## Resumen profesional\nMás de 2 años de experiencia. ", "2"),
        ("Despliegue de servicios con Docker", "Despliegue de servicios 3x más rápido con Docker", "3"),
    ],
)
def test_detects_invented_metrics(original, invented, term):
    report = validate(FAITHFUL_CV.replace(original, invented, 1))
    assert ("UNGROUNDED_METRIC", term) in codes(report)


def test_versions_and_language_levels_are_not_metrics():
    # B2, ES6, S3... son niveles/versiones pegados a letras: no se tratan como cifras.
    report = validate(FAITHFUL_CV.replace("Inglés (B2)", "Inglés (nivel B2)"))
    assert not [w for w in report.warnings if w.code == "UNGROUNDED_METRIC"]


def test_detects_invented_company_and_degree():
    markdown = FAITHFUL_CV.replace("Beta Consulting", "Google Spain").replace(
        "Grado en Ingeniería Informática", "Máster en Inteligencia Artificial"
    )
    found = codes(validate(markdown))
    assert ("UNGROUNDED_ENTITY", "Google Spain") in found
    assert ("UNGROUNDED_ENTITY", "Máster en Inteligencia Artificial") in found


def test_detects_exaggerated_job_title():
    found = codes(validate(FAITHFUL_CV.replace("Programadora junior", "Tech Lead")))
    assert ("UNGROUNDED_ENTITY", "Tech Lead") in found


def test_detects_invented_email_and_profile_url():
    markdown = FAITHFUL_CV.replace(
        "ana.garcia@example.com", "ana@otra.com · linkedin.com/in/ana-garcia"
    )
    found = codes(validate(markdown))
    assert ("UNGROUNDED_ENTITY", "ana@otra.com") in found
    assert ("UNGROUNDED_ENTITY", "linkedin.com/in/ana-garcia") in found


def test_detects_invented_skill():
    report = validate(FAITHFUL_CV.replace("Python, FastAPI, Django", "Python, FastAPI, Django, Rust"))
    assert ("UNGROUNDED_SKILL", "Rust") in codes(report)


def test_skill_qualifier_that_inflates_level_is_flagged():
    report = validate(FAITHFUL_CV.replace("Inglés (B2)", "Inglés nativo"))
    assert ("UNGROUNDED_SKILL", "Inglés nativo") in codes(report)


def test_truthful_synonyms_and_plurals_are_accepted():
    markdown = FAITHFUL_CV.replace("Python, FastAPI, Django", "Py, FastAPI, Django").replace(
        "PostgreSQL\n- **DevOps", "Postgres\n- **DevOps"
    )
    assert validate(markdown).ungrounded_count == 0


def test_offer_requirement_leaked_into_cv():
    markdown = FAITHFUL_CV.replace("Docker, Git, GitHub Actions", "Docker, Kubernetes, Git")
    report = validate(markdown)
    found = codes(report)
    assert ("GAP_LEAKED", "Kubernetes") in found
    assert ("UNGROUNDED_SKILL", "Kubernetes") not in found  # un solo aviso por término
    assert report.leaked_keywords == {"Kubernetes"}


def test_keywords_already_in_cv_are_not_leaks():
    assert validate(FAITHFUL_CV, keywords=["Docker", "APIs REST", "FastAPI"]).leaked_keywords == set()


def test_format_warnings_do_not_count_as_hallucinations():
    markdown = FAITHFUL_CV + "\n| a | b |\n|---|---|\n![foto](x.png)\n"
    report = validate(markdown)
    assert {w.term for w in report.warnings if w.code == "FORMAT"} >= {"tabla", "imagen"}
    assert report.ungrounded_count == 0


def test_translated_cv_skips_language_dependent_checks_but_keeps_hard_facts():
    english = """# Ana Garcia Lopez
## Professional summary
Backend developer with experience in the design of REST APIs with FastAPI and the deployment of
services with Docker, with a 50% improvement in the response time of the API.
## Experience
### Python Developer — Acme Software SL
*2018 – Present*
- Development of REST APIs with FastAPI and PostgreSQL.
## Skills
- Python, FastAPI, Django, Docker, Git
"""
    found = codes(validate(english))
    assert ("LIMITED_CHECK", "idioma") in found
    assert ("UNGROUNDED_DATE", "2018") in found  # los hechos duros se siguen validando
    assert ("UNGROUNDED_METRIC", "50") in found
    assert not [c for c, _ in found if c in {"UNGROUNDED_ENTITY", "UNGROUNDED_SKILL"}]


def test_warnings_include_snippet_for_the_ui():
    report = validate(FAITHFUL_CV.replace("en un 30%", "en un 45%"))
    warning = next(w for w in report.warnings if w.term == "45")
    assert "45%" in warning.snippet


def test_source_index_grounding():
    source = SourceIndex(SOURCE_CV)
    assert source.is_grounded("Universidad Complutense de Madrid")
    assert source.is_grounded("APIs REST")
    assert source.is_grounded("javascript") is False
    assert source.is_grounded("Java") is False  # no basta con ser prefijo de otra palabra


def test_detect_language():
    assert detect_language(FAITHFUL_CV) == "es"
    assert detect_language("Experience with the design and development of APIs for the team") == "en"


# --- Afirmaciones del resumen ------------------------------------------------------------------

REAL_SUMMARY = (  # Resumen real devuelto por gpt-oss-120b en producción (13/10/2026).
    "## Resumen profesional\n"
    "Desarrolladora Backend con experiencia creando APIs REST con Python y FastAPI, gestionando bases de "
    "datos PostgreSQL y desplegando contenedores Docker. Orientada a la mejora continua y al trabajo "
    "autónomo en entornos colaborativos.\n"
)


def claims(report) -> list[str]:
    return [w.term for w in report.warnings if w.code == "UNGROUNDED_CLAIM"]


def test_invented_soft_skills_in_summary_are_flagged():
    report = validate(REAL_SUMMARY)
    invented = "Orientada a la mejora continua y al trabajo autónomo en entornos colaborativos"
    assert claims(report) == [invented]
    assert report.ungrounded_count == 1  # cuenta como dato no respaldado: dispara la corrección


def test_rewording_real_facts_in_summary_is_not_flagged():
    # "gestionando bases de datos PostgreSQL" se ancla en PostgreSQL; no es una invención.
    summary = REAL_SUMMARY.split(". Orientada")[0] + ".\n"
    assert claims(validate(summary)) == []


def test_invented_clause_after_comma_is_flagged():
    summary = "## Perfil\nDesarrolladora backend con Python, orientada a resultados y liderazgo de equipos.\n"
    assert claims(validate(summary)) == ["orientada a resultados y liderazgo de equipos"]


def test_neutral_wording_and_short_lists_are_not_claims():
    summary = "## Resumen\nProfesional con amplia experiencia. Python, FastAPI, Django.\n"
    assert claims(validate(summary)) == []


def test_claims_are_only_checked_in_the_summary_section():
    text = "## Experiencia\n- Orientada a la mejora continua y al trabajo autónomo en equipos.\n"
    assert claims(validate(text)) == []


def test_faithful_cv_summary_has_no_claims():
    assert claims(validate(FAITHFUL_CV)) == []
