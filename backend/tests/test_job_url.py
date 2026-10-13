"""Ofertas desde URL: Jina Reader, detección de muros y validación de la URL."""

import httpx
import pytest
import respx

from app.core.exceptions import InvalidJobUrlError
from app.services.job_url_extractor import clean_text, looks_like_job_offer, validate_url

OFFER_URL = "https://empleo.example.com/ofertas/123"
JINA_PAGE = (
    "Title: Auxiliar administrativo/a\n\nURL Source: https://empleo.example.com/ofertas/123\n\n"
    "Markdown Content:\n![logo](https://x/logo.png)\n[Inicio](https://x) [Empleos](https://x)\n\n\n\n"
    "# Auxiliar administrativo/a\n\nBuscamos auxiliar administrativo para nuestra oficina de Sevilla.\n\n"
    "## Funciones\n- Contabilidad y facturación.\n- Gestión laboral.\n\n"
    "## Requisitos\n- FP de Administración y Finanzas.\n- 2 años de experiencia.\n- Excel medio.\n\n"
    "## Ofrecemos\n- Contrato indefinido y jornada completa.\n\n"
    "Utilizamos cookies para mejorar tu experiencia."
)
LINKEDIN_WALL = (
    "Join LinkedIn\nSign in\nPage not found\nUh oh, we can't seem to find the page you're looking for. "
    "Try going back to the previous page or see our Help Center for more information. Go to your feed. "
    "User Agreement Privacy Policy Community Guidelines Cookie Policy Copyright Policy Guest Controls"
)
COOKIE_WALL = (
    "With your agreement, we and our 1037 partners use cookies or similar technologies to store, access, "
    "and process personal data like your visit on this website, IP addresses and cookie identifiers. "
    "Some partners do not ask for your consent to process your data and rely on their legitimate interest."
)


@pytest.fixture
def jina_mock():
    with respx.mock(base_url="https://r.jina.ai", assert_all_called=False) as mock:
        yield mock


def post_url(client, url=OFFER_URL):
    return client.post("/api/v1/extract-job-url", json={"url": url})


def test_extracts_and_cleans_the_offer(client, jina_mock):
    route = jina_mock.get(f"/{OFFER_URL}").mock(return_value=httpx.Response(200, text=JINA_PAGE))

    response = post_url(client)

    assert response.status_code == 200
    text = response.json()["text"]
    assert text.startswith("Inicio Empleos")  # cabecera de Jina, imágenes y enlaces fuera
    assert "Title:" not in text and "logo" not in text and "\n\n\n" not in text
    assert "Excel medio" in text
    assert route.calls[0].request.headers["X-Return-Format"] == "text"


@pytest.mark.parametrize("status", [403, 429, 451, 500])
def test_blocked_portal_returns_422_with_instructions(client, jina_mock, status):
    jina_mock.get(f"/{OFFER_URL}").mock(return_value=httpx.Response(status, text="blocked"))

    response = post_url(client)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "JOB_URL_UNREADABLE"
    assert "Ctrl+A" in error["message"] and "Ctrl+V" in error["message"]


@pytest.mark.parametrize("page", [LINKEDIN_WALL, COOKIE_WALL])
def test_login_or_cookie_wall_with_status_200_is_rejected(client, jina_mock, page):
    """Jina responde 200 aunque el portal muestre un muro: se detecta por el contenido."""
    jina_mock.get(f"/{OFFER_URL}").mock(return_value=httpx.Response(200, text=page))

    assert post_url(client).json()["error"]["code"] == "JOB_URL_UNREADABLE"


def test_timeout_is_reported_as_unreadable(client, jina_mock):
    jina_mock.get(f"/{OFFER_URL}").mock(side_effect=httpx.ReadTimeout("slow"))

    assert post_url(client).json()["error"]["code"] == "JOB_URL_UNREADABLE"


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "javascript:alert(1)", "https://localhost/admin", "http://127.0.0.1:8000/",
     "http://192.168.1.10/oferta", "http://[::1]/", "https://intranet.local/oferta", "no es una url"],
)
def test_rejects_non_public_urls(url):
    with pytest.raises(InvalidJobUrlError):
        validate_url(url)


def test_invalid_url_never_reaches_jina(client, jina_mock):
    route = jina_mock.route().mock(return_value=httpx.Response(200, text=JINA_PAGE))

    response = post_url(client, "http://10.0.0.5/oferta")

    assert response.json()["error"]["code"] == "INVALID_JOB_URL"
    assert route.call_count == 0


def test_rate_limited_per_ip(jina_mock):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import make_settings

    jina_mock.get(f"/{OFFER_URL}").mock(return_value=httpx.Response(200, text=JINA_PAGE))
    with TestClient(create_app(make_settings(job_url_per_minute=2))) as client:
        assert [post_url(client).status_code for _ in range(3)] == [200, 200, 429]


def test_clean_text_caps_length_and_collapses_blank_lines():
    text = clean_text("a   b\n\n\n\n\nc" + "x" * 20_000)
    assert text.startswith("a b\n\nc")
    assert len(text) == 10_000


def test_offer_detection_needs_several_offer_markers():
    assert looks_like_job_offer(clean_text(JINA_PAGE), min_chars=200)
    listing = "Open Roles\nCreate a Job Alert\n647 jobs\n" + "Engineer, San Francisco\n" * 20
    assert not looks_like_job_offer(listing, min_chars=200)
