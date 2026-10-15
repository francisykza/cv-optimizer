"""SDD 1.6: filtro de cookies, nivel de ajuste, pitch de candidatura y resumen informativo."""

import json

from app.services.consent_filter import strip_consent_noise
from app.services.prompt_builder import PromptBuilder
from tests.conftest import groq_completion, llm_payload
from tests.pdf_factory import SAMPLE_JOB_OFFER as OFFER
from tests.test_api import post_optimize

COOKIE_BANNER = (
    "With your agreement, we and our 1037 partners use cookies or similar technologies to store, access, "
    "and process personal data like your visit on this website, IP addresses and cookie identifiers.\n"
    "We and our partners process data for the following purposes:\n"
    "Personalised advertising and content, advertising and content measurement, audience research\n"
    "Aceptar todo\n"
    "Rechazar"
)


def test_cookie_banner_is_removed_and_offer_lines_are_kept():
    offer = (
        COOKIE_BANNER + "\n\nAuxiliar administrativo/a\n"
        "Requisitos: experiencia en RGPD y protección de datos personales.\n"
        "Valoramos conocimientos de consentimiento informado en clínicas."
    )
    cleaned = strip_consent_noise(offer)

    assert "partners" not in cleaned and "Aceptar todo" not in cleaned and "Rechazar" not in cleaned
    # Una oferta de protección de datos no es un banner: se conservan sus líneas.
    assert "RGPD y protección de datos personales" in cleaned
    assert "consentimiento informado" in cleaned


def test_spanish_cookie_notice_is_removed():
    text = "Utilizamos cookies propias y de terceros para fines analíticos.\nBuscamos dependiente/a."
    assert strip_consent_noise(text) == "Buscamos dependiente/a."


def test_offer_sent_to_the_llm_has_no_cookie_banner(client, groq_mock):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))

    response = post_optimize(client, offer=COOKIE_BANNER + "\n\n" + OFFER)

    assert response.status_code == 200
    user_prompt = json.loads(route.calls[0].request.content)["messages"][1]["content"]
    assert "1037 partners" not in user_prompt
    assert OFFER[:60] in user_prompt


def test_adjustment_level_changes_the_prompt():
    builder = PromptBuilder()
    subtle = builder.build("cv", "oferta", "es", "subtle").system
    deep = builder.build("cv", "oferta", "es", "deep").system
    assert "SUTIL" in subtle and "PROFUNDO" not in subtle
    assert "[Acción] + [Herramienta] + [Resultado]" in deep
    assert "NUNCA inventes el resultado" in deep
    assert "{{" not in subtle + deep


def test_adjustment_level_is_sent_from_the_form(client, groq_mock):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))

    post_optimize(client, extra={"adjustment_level": "subtle"})

    system = json.loads(route.calls[0].request.content)["messages"][0]["content"]
    assert "SUTIL" in system


def test_invalid_adjustment_level_is_rejected(client, groq_mock):
    response = post_optimize(client, extra={"adjustment_level": "extremo"})
    assert response.status_code == 422


PITCH = (
    "Desarrolladora backend con Python y FastAPI, encaja con lo que buscáis.\n"
    "- APIs REST con FastAPI.\n- Bases de datos PostgreSQL.\n- Contenedores Docker."
)


def test_pitch_is_returned(client, groq_mock):
    groq_mock.post("/chat/completions").mock(
        return_value=groq_completion(llm_payload(application_pitch=PITCH))
    )

    body = post_optimize(client).json()

    assert body["application_pitch"] == PITCH
    assert body["quality"] == "ok"


def test_invented_data_in_the_pitch_triggers_the_correction(client, groq_mock):
    invented = PITCH + "\n- Reduje un 45% los tiempos de despliegue con Kubernetes."
    route = groq_mock.post("/chat/completions").mock(
        side_effect=[
            groq_completion(llm_payload(application_pitch=invented)),
            groq_completion(llm_payload(application_pitch=PITCH)),
        ]
    )

    body = post_optimize(client).json()

    assert route.call_count == 2
    correction = json.loads(route.calls[1].request.content)["messages"][-1]["content"]
    assert "En el pitch" in correction and "45" in correction and "Kubernetes" in correction
    assert body["application_pitch"] == PITCH
    assert body["quality"] == "ok"


def test_summary_filler_is_reported_without_forcing_a_correction(client, groq_mock):
    markdown = llm_payload()["optimized_markdown"].replace(
        "PostgreSQL.\n\n## Experiencia",
        "PostgreSQL. Orientada a la mejora continua en entornos colaborativos.\n\n## Experiencia",
    )
    route = groq_mock.post("/chat/completions").mock(
        return_value=groq_completion(llm_payload(optimized_markdown=markdown))
    )

    body = post_optimize(client).json()

    assert route.call_count == 1  # no se pide corrección
    assert body["quality"] == "ok"
    assert [w["code"] for w in body["warnings"]] == ["UNGROUNDED_CLAIM"]
