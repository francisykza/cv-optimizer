"""Regresiones vistas en producción con el modelo de reserva (openai/gpt-oss-20b, 15/10/2026)."""

from app.services.match_scorer import contains, dropped_keywords, score
from app.services.output_validator import OutputValidator

SOURCE = (
    "Laura Perez Gil\nAuxiliar administrativa - Sevilla\nEXPERIENCIA\n"
    "Gestoria Sur SL - Auxiliar administrativa (2022 - Actualidad)\n"
    "- Contabilidad y facturacion de clientes con Contanet.\n- Gestion Laboral: altas, bajas y nominas.\n"
    "FORMACION\nFPI Administracion y Finanzas - IES Triana (2020 - 2022)\nHABILIDADES\nContanet, Excel"
)
# El 20b puso tildes que el PDF no tenía y usó "# Sección" (nivel 1) para las secciones.
OUTPUT_20B = (
    "# Laura Perez Gil\n\n# Resumen profesional\n"
    "Auxiliar administrativa con FPI Administración y Finanzas y experiencia en contabilidad, "
    "facturación y gestión laboral.\n\n"
    "# Experiencia\n## Gestoria Sur SL - Auxiliar administrativa (2022 - Actualidad)\n"
    "- Contabilidad y facturación de clientes con Contanet.\n- Gestión Laboral: altas, bajas y nóminas.\n\n"
    "# Formación\n**FPI Administración y Finanzas** - IES Triana (2020 - 2022)\n\n"
    "# Habilidades\nContanet, Excel"
)
KEYWORDS = ["FPI Administracion y Finanzas", "contabilidad", "facturacion", "Contanet", "Excel medio"]


def test_adding_accents_is_not_dropping_a_keyword():
    assert contains("FPI Administración y Finanzas", "FPI Administracion y Finanzas")
    assert dropped_keywords(KEYWORDS, SOURCE, OUTPUT_20B) == []
    report = score(KEYWORDS, SOURCE, OUTPUT_20B)
    assert report.score_after == report.score_before  # antes bajaba de 75 % a 50 %


def test_level_one_section_headings_are_not_invented_entities():
    report = OutputValidator().validate(OUTPUT_20B, SOURCE, KEYWORDS)
    assert report.ungrounded_count == 0, [w.message for w in report.ungrounded]


def test_invented_company_under_level_one_sections_is_still_flagged():
    invented = OUTPUT_20B.replace("## Gestoria Sur SL", "## Deloitte Consulting")
    report = OutputValidator().validate(invented, SOURCE, KEYWORDS)
    assert any("Deloitte" in (w.term or "") for w in report.ungrounded)


def test_personality_traits_in_the_pitch_are_reported_as_informative():
    pitch = "Cumplo las tareas de contabilidad de forma organizada y proactiva.\n- Contanet."
    traits = ["proactiva", "organizada", "dinamica"]
    warnings = OutputValidator().validate_pitch(pitch, SOURCE, KEYWORDS, traits)
    assert [(w.code, w.message.startswith("En el pitch:")) for w in warnings] == [
        ("UNGROUNDED_CLAIM", True),
        ("UNGROUNDED_CLAIM", True),
    ]
    assert "dinamica" not in " ".join(w.message for w in warnings)
