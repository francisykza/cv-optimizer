from app.services.change_detector import detect_changes
from tests.pdf_factory import SAMPLE_CV_LINES

SOURCE_CV = "\n".join(SAMPLE_CV_LINES)


def test_rewording_is_detected_as_a_phrase():
    markdown = "## Experiencia\n- Diseñé y mantuve APIs REST con FastAPI y PostgreSQL."
    changes = detect_changes(markdown, SOURCE_CV)
    assert "Diseñé y mantuve" in changes
    # Lo que ya estaba (APIs REST, FastAPI, PostgreSQL) no se marca.
    assert not any("FastAPI" in c or "PostgreSQL" in c for c in changes)


def test_reordering_without_rewording_is_not_a_change():
    reordered = "\n".join(reversed(SAMPLE_CV_LINES))
    assert detect_changes(reordered, SOURCE_CV) == []


def test_stopwords_alone_are_never_highlighted():
    assert detect_changes("de la con para y en", SOURCE_CV) == []


def test_accents_case_and_plurals_do_not_count_as_changes():
    # El CV original dice "Desarrollo de APIs REST" y "aplicaciones Django" (sin tildes).
    assert detect_changes("- DESARROLLO de la API REST y aplicación Django", SOURCE_CV) == []


def test_truthful_synonyms_are_not_changes():
    assert detect_changes("Py, Postgres", SOURCE_CV) == []


def test_ungrounded_terms_stay_amber_and_split_phrases():
    markdown = "- Orquestación con Kubernetes en producción."
    changes = detect_changes(markdown, SOURCE_CV, exclude=["Kubernetes"])
    assert not any("Kubernetes" in c for c in changes)
    assert "Orquestación" in changes


def test_phrases_never_cross_markdown_formatting():
    # El frontend resalta dentro de cada nodo de texto: "**Liderazgo** técnico" son dos nodos.
    changes = detect_changes("- **Liderazgo** técnico", SOURCE_CV)
    assert changes == ["Liderazgo", "técnico"]


def test_numbers_are_left_to_the_validator():
    assert detect_changes("- Reducción del tiempo de respuesta en un 45%", SOURCE_CV) == []


def test_headings_and_list_markers_are_ignored_but_their_words_count():
    changes = detect_changes("## Resumen profesional\n1. Orientada a resultados", SOURCE_CV)
    assert changes == ["Resumen profesional", "Orientada a resultados"]


def test_duplicates_are_removed_and_limit_is_respected():
    markdown = "Liderazgo\nliderazgo\n" + "\n".join(f"palabra{i}x" for i in range(200))
    changes = detect_changes(markdown, SOURCE_CV, limit=10)
    assert changes[0] == "Liderazgo"
    assert len(changes) == 10
