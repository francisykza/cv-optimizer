import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import (
    FRONTEND_ORIGIN,
    SERVER_KEY,
    USER_KEY,
    groq_completion,
    llm_payload,
    make_settings,
)
from tests.pdf_factory import SAMPLE_CV_PDF, SAMPLE_JOB_OFFER, make_pdf


def post_optimize(client, pdf=SAMPLE_CV_PDF, offer=SAMPLE_JOB_OFFER, headers=None, filename="cv.pdf",
                  content_type="application/pdf", language="auto"):
    return client.post(
        "/api/v1/optimize",
        files={"cv_file": (filename, pdf, content_type)},
        data={"job_offer": offer, "output_language": language},
        headers=headers or {},
    )


# --- /health ---------------------------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["server_llm_available"] is True
    assert response.headers["x-request-id"]


# --- /optimize: camino feliz ------------------------------------------------------------------

def test_optimize_with_server_key(client, groq_mock):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))

    response = post_optimize(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["optimized_markdown"].startswith("# Ana Garcia Lopez")
    assert body["meta"]["mode"] == "server"
    assert body["meta"]["model"] == "primary-model"
    assert body["meta"]["pdf_pages"] == 1
    assert body["gaps"][0] == "Kubernetes"
    # "Rust" no aparece en la oferta: se descarta. 4 de 6 keywords cubiertas tras optimizar.
    assert "Rust" not in body["match"]["matched_keywords"] + body["match"]["missing_keywords"]
    assert body["match"]["score_after"] == 67
    assert response.headers["cache-control"] == "no-store"

    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {SERVER_KEY}"
    payload = json.loads(sent.content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.2
    assert "PROHIBIDO INVENTAR" in payload["messages"][0]["content"]
    assert "Acme Software SL" in payload["messages"][1]["content"]  # el texto del PDF llegó al prompt


def test_optimize_byok_uses_user_key(client, groq_mock):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))

    response = post_optimize(client, headers={"X-User-API-Key": USER_KEY, "X-LLM-Provider": "groq"})

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["mode"] == "byok"
    assert route.calls.last.request.headers["authorization"] == f"Bearer {USER_KEY}"


def test_server_key_pasted_with_whitespace_is_cleaned(groq_mock):
    """Regresión: el textarea de Render añadió un salto de línea a la clave y httpx rechazaba la
    cabecera Authorization sin llegar a contactar con Groq."""
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    with TestClient(create_app(make_settings(groq_api_key=f"  {SERVER_KEY}\n"))) as client:
        response = post_optimize(client)

    assert response.status_code == 200, response.text
    assert route.calls.last.request.headers["authorization"] == f"Bearer {SERVER_KEY}"


def test_reasoning_effort_only_sent_to_reasoning_models(groq_mock):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    settings = make_settings(groq_model_primary="openai/gpt-oss-120b", llm_reasoning_effort="low")
    with TestClient(create_app(settings)) as client:
        assert post_optimize(client).status_code == 200
    assert json.loads(route.calls.last.request.content)["reasoning_effort"] == "low"

    # Con un modelo que no razona no se envía (Groq respondería 400).
    with TestClient(create_app(make_settings(llm_reasoning_effort="low"))) as client:
        assert post_optimize(client).status_code == 200
    assert "reasoning_effort" not in json.loads(route.calls.last.request.content)


def test_byok_works_without_server_key(groq_mock):
    groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    with TestClient(create_app(make_settings(groq_api_key=""))) as client:
        assert post_optimize(client).json()["error"]["code"] == "SERVER_LLM_NOT_CONFIGURED"
        assert post_optimize(client, headers={"X-User-API-Key": USER_KEY}).status_code == 200


def test_optimize_repairs_invalid_json_once(client, groq_mock):
    groq_mock.post("/chat/completions").mock(
        side_effect=[groq_completion("esto no es json"), groq_completion(llm_payload())]
    )
    response = post_optimize(client)
    assert response.status_code == 200
    assert response.json()["meta"]["tokens"] == {"input": 2000, "output": 800}


def test_optimize_fails_after_two_invalid_outputs(client, groq_mock):
    groq_mock.post("/chat/completions").mock(return_value=groq_completion("```json\n{roto"))
    response = post_optimize(client)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_OUTPUT"


# --- Validador anti-alucinación en el flujo completo ------------------------------------------

INVENTED_MARKDOWN = (
    "# Ana Garcia Lopez\n\n## Resumen profesional\nMas de 8 anos de experiencia con Python.\n\n"
    "## Experiencia\n### Acme Software SL\n*2017 - Actualidad*\n- APIs REST con FastAPI.\n\n"
    "## Habilidades\nPython, FastAPI, PostgreSQL, Docker, Kubernetes"
)


def test_invented_data_triggers_one_correction(client, groq_mock):
    route = groq_mock.post("/chat/completions").mock(
        side_effect=[
            groq_completion(llm_payload(optimized_markdown=INVENTED_MARKDOWN)),
            groq_completion(llm_payload()),  # versión corregida y fiel
        ]
    )

    response = post_optimize(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quality"] == "ok"
    assert body["warnings"] == []
    assert route.call_count == 2
    correction = json.loads(route.calls[1].request.content)["messages"]
    assert correction[-2]["role"] == "assistant"  # se le devuelve su respuesta anterior...
    assert "PROHIBIDO INVENTAR" in correction[-1]["content"]  # ...con la lista de lo no respaldado
    for item in ("Kubernetes", "2017", "8"):
        assert f"- {item}" in correction[-1]["content"]


def test_persistent_hallucinations_are_flagged_for_review(client, groq_mock):
    groq_mock.post("/chat/completions").mock(
        return_value=groq_completion(llm_payload(optimized_markdown=INVENTED_MARKDOWN))
    )

    body = post_optimize(client).json()

    assert body["quality"] == "needs_review"
    flagged = {(w["code"], w["term"]) for w in body["warnings"]}
    assert {("GAP_LEAKED", "Kubernetes"), ("UNGROUNDED_DATE", "2017"), ("UNGROUNDED_METRIC", "8")} <= flagged
    # La puntuación no sube a base de inventar: Kubernetes no cuenta como cubierta.
    assert "Kubernetes" in body["match"]["missing_keywords"]
    assert "Kubernetes" not in body["match"]["matched_keywords"]


def test_failed_correction_keeps_original_result_with_warnings(client, groq_mock):
    groq_mock.post("/chat/completions").mock(
        side_effect=[
            groq_completion(llm_payload(optimized_markdown=INVENTED_MARKDOWN)),
            httpx.ReadTimeout("timeout"),
        ]
    )

    response = post_optimize(client)

    assert response.status_code == 200
    assert response.json()["quality"] == "needs_review"
    assert response.json()["warnings"]


# --- Resiliencia del proveedor ----------------------------------------------------------------

def test_server_mode_falls_back_to_second_model_on_rate_limit(client, groq_mock):
    def respond(request):
        model = json.loads(request.content)["model"]
        if model == "primary-model":
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        return groq_completion(llm_payload(), model="fallback-model")

    route = groq_mock.post("/chat/completions").mock(side_effect=respond)
    response = post_optimize(client)

    assert response.status_code == 200
    assert response.json()["meta"]["model"] == "fallback-model"
    assert route.call_count == 4  # 3 intentos con el principal (1 + 2 reintentos) + 1 con el de reserva


def test_invalid_byok_key_returns_401(client, groq_mock):
    groq_mock.post("/chat/completions").mock(return_value=httpx.Response(401, json={"error": {}}))
    response = post_optimize(client, headers={"X-User-API-Key": USER_KEY})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BYOK_KEY_INVALID"
    assert USER_KEY not in response.text


def test_llm_timeout_returns_504(client, groq_mock):
    groq_mock.post("/chat/completions").mock(side_effect=httpx.ReadTimeout("timeout"))
    response = post_optimize(client)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "LLM_TIMEOUT"


# --- Validación de entrada --------------------------------------------------------------------

@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"offer": "demasiado corta"}, 422, "INVALID_JOB_OFFER"),
        ({"pdf": b"%PDF-1.4 roto"}, 400, "INVALID_PDF"),
        ({"pdf": b"MZ\x90\x00 exe", "filename": "cv.pdf"}, 400, "INVALID_PDF"),
        ({"pdf": make_pdf([[]])}, 422, "PDF_NO_TEXT"),
        ({"content_type": "image/png", "filename": "cv.png"}, 415, "UNSUPPORTED_MEDIA_TYPE"),
        ({"headers": {"X-LLM-Provider": "openai", "X-User-API-Key": USER_KEY}}, 422, "INVALID_PROVIDER"),
        ({"headers": {"X-User-API-Key": "corta"}}, 422, "INVALID_API_KEY_FORMAT"),
        ({"language": "fr"}, 422, "VALIDATION_ERROR"),
    ],
)
def test_input_validation(client, groq_mock, kwargs, status, code):
    route = groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    response = post_optimize(client, **kwargs)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert not route.called  # nunca se llega al LLM con entradas inválidas


def test_missing_file_returns_validation_error(client):
    response = client.post("/api/v1/optimize", data={"job_offer": SAMPLE_JOB_OFFER})
    assert response.status_code == 422
    assert "cv_file" in response.json()["error"]["message"]


def test_accepts_octet_stream_with_pdf_extension(client, groq_mock):
    groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    assert post_optimize(client, content_type="application/octet-stream").status_code == 200


def test_rejects_oversized_upload_with_413():
    with TestClient(create_app(make_settings(max_upload_mb=1))) as client:
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        response = post_optimize(client, pdf=big, headers={"Origin": FRONTEND_ORIGIN})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    # Incluso los errores del middleware llevan CORS, para que el navegador pueda leerlos.
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_rate_limit_applies_only_to_server_mode(groq_mock):
    groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    with TestClient(create_app(make_settings(rate_limit_per_minute=2))) as client:
        assert post_optimize(client).status_code == 200
        assert post_optimize(client).status_code == 200
        limited = post_optimize(client)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"
        assert int(limited.headers["retry-after"]) > 0
        # Con clave propia no se aplica el límite del servidor.
        assert post_optimize(client, headers={"X-User-API-Key": USER_KEY}).status_code == 200


# --- /keys/validate ---------------------------------------------------------------------------

def test_validate_key_valid(client, groq_mock):
    route = groq_mock.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))
    response = client.post("/api/v1/keys/validate", headers={"X-User-API-Key": USER_KEY})
    assert response.status_code == 200
    assert response.json() == {"valid": True, "provider": "groq"}
    assert route.calls.last.request.headers["authorization"] == f"Bearer {USER_KEY}"


def test_validate_key_invalid(client, groq_mock):
    groq_mock.get("/models").mock(return_value=httpx.Response(401, json={"error": {}}))
    response = client.post("/api/v1/keys/validate", headers={"X-User-API-Key": USER_KEY})
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_validate_key_requires_header(client):
    response = client.post("/api/v1/keys/validate")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_API_KEY_FORMAT"


def test_validate_key_is_rate_limited(groq_mock):
    groq_mock.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))
    with TestClient(create_app(make_settings(key_validation_per_minute=1))) as client:
        headers = {"X-User-API-Key": USER_KEY}
        assert client.post("/api/v1/keys/validate", headers=headers).status_code == 200
        assert client.post("/api/v1/keys/validate", headers=headers).status_code == 429


# --- CORS -------------------------------------------------------------------------------------

def test_cors_preflight_allows_frontend_with_byok_header(client):
    response = client.options(
        "/api/v1/optimize",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-user-api-key,x-llm-provider",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "x-user-api-key" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_unknown_origin(client):
    response = client.options(
        "/api/v1/optimize",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_cors_headers_on_error_responses(client):
    response = client.post("/api/v1/keys/validate", headers={"Origin": FRONTEND_ORIGIN})
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
