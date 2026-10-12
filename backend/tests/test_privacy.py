"""Garantías de privacidad del SDD: ningún archivo de usuario toca el disco y las claves no se registran."""

import logging
import re
import tempfile
from pathlib import Path

from tests.conftest import USER_KEY, groq_completion, llm_payload
from tests.pdf_factory import SAMPLE_CV_LINES, SAMPLE_JOB_OFFER, make_pdf

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def test_large_upload_is_never_spooled_to_disk(client, groq_mock, monkeypatch):
    """Starlette pasa los uploads a disco al superar spool_max_size (1 MB por defecto).
    Con un PDF de ~4,5 MB comprobamos que eso nunca ocurre."""
    rollovers = []
    original = tempfile.SpooledTemporaryFile.rollover

    def spy(self):
        rollovers.append(True)
        return original(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", spy)
    groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))

    # PDF válido con mucho relleno para superar con creces 1 MB.
    pdf = make_pdf([SAMPLE_CV_LINES], padding_bytes=4_500_000)
    response = client.post(
        "/api/v1/optimize",
        files={"cv_file": ("cv.pdf", pdf, "application/pdf")},
        data={"job_offer": SAMPLE_JOB_OFFER},
    )

    assert len(pdf) > 4_000_000
    assert response.status_code == 200, response.text
    assert rollovers == [], "El PDF se escribió en disco"


def test_app_code_never_writes_files():
    """Test de arquitectura: el código de la app no usa APIs que escriban en disco."""
    forbidden = re.compile(
        r"^\s*(import|from)\s+tempfile\b|NamedTemporaryFile\(|mkstemp\(|\.write_bytes\(|\.write_text\(|"
        r"open\([^)]*['\"][wax]b?\+?['\"]"
    )
    offenders = [
        f"{path.relative_to(APP_DIR)}:{lineno}: {line.strip()}"
        for path in APP_DIR.rglob("*.py")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if forbidden.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == []


def test_user_key_and_cv_content_never_logged(client, groq_mock, caplog):
    groq_mock.post("/chat/completions").mock(return_value=groq_completion(llm_payload()))
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/api/v1/optimize",
        files={"cv_file": ("cv.pdf", make_pdf([SAMPLE_CV_LINES]), "application/pdf")},
        data={"job_offer": SAMPLE_JOB_OFFER},
        headers={"X-User-API-Key": USER_KEY},
    )
    assert response.status_code == 200

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "optimize_done" in logs  # se registran metadatos...
    assert USER_KEY not in logs  # ...pero nunca la clave
    assert "Acme Software SL" not in logs  # ni el contenido del CV
    assert "teletrabajo" not in logs  # ni el de la oferta


def test_log_filter_redacts_keys_that_slip_through():
    from app.core.logging import redact

    assert USER_KEY not in redact(f"error con la clave {USER_KEY}")
    assert "[REDACTED]" in redact("Authorization: Bearer abcdefghijklmnop")
