import io

import pytest
from pypdf import PdfReader, PdfWriter

from app.core.exceptions import InvalidPdfError, PdfNoTextError, TooManyPagesError
from app.services.pdf_extractor import PdfExtractor
from app.services.text_normalizer import normalize
from tests.pdf_factory import SAMPLE_CV_LINES, SAMPLE_CV_PDF, make_pdf


@pytest.fixture
def extractor() -> PdfExtractor:
    return PdfExtractor(max_pages=5, min_chars=200, max_chars=30_000)


def test_extracts_text_from_valid_pdf(extractor):
    result = extractor.extract(SAMPLE_CV_PDF)
    assert result.pages == 1
    assert "Acme Software SL" in result.text
    assert "FastAPI y PostgreSQL" in result.text


def test_rejects_non_pdf(extractor):
    with pytest.raises(InvalidPdfError):
        extractor.extract(b"esto no es un pdf" * 100)


def test_rejects_corrupt_pdf(extractor):
    with pytest.raises(InvalidPdfError):
        extractor.extract(b"%PDF-1.4\n" + b"\x00garbage" * 50)


def test_detects_scanned_pdf_without_text(extractor):
    with pytest.raises(PdfNoTextError):
        extractor.extract(make_pdf([[]]))


def test_rejects_too_many_pages(extractor):
    with pytest.raises(TooManyPagesError):
        extractor.extract(make_pdf([SAMPLE_CV_LINES] * 6))


def _encrypt(data: bytes, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_rejects_password_protected_pdf(extractor):
    with pytest.raises(InvalidPdfError):
        extractor.extract(_encrypt(SAMPLE_CV_PDF, user_password="secret"))


def test_accepts_pdf_with_empty_user_password(extractor):
    result = extractor.extract(_encrypt(SAMPLE_CV_PDF, user_password=""))
    assert "Acme Software SL" in result.text


def test_truncates_very_long_text():
    extractor = PdfExtractor(max_pages=5, min_chars=10, max_chars=100)
    assert len(extractor.extract(SAMPLE_CV_PDF).text) == 100


def test_normalize():
    raw = "Desarro-\nllo de ﬁcheros\r\n•  Python\n\n\n\n“Docker”\x07"
    assert normalize(raw) == 'Desarrollo de ficheros\n- Python\n\n"Docker"'
