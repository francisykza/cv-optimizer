"""Extracción de texto de PDFs 100 % en memoria.

Privacidad: los bytes llegan como `bytes`, se envuelven en `io.BytesIO` y nunca se
escriben en disco (ni `tempfile`, ni `open()`). Cuando la función termina, todo queda
fuera de scope y lo recoge el GC.
"""

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

from app.core.exceptions import InvalidPdfError, PdfNoTextError, TooManyPagesError
from app.services.text_normalizer import normalize

PDF_MAGIC = b"%PDF-"

# pypdf avisa por logging de cada irregularidad del PDF; no aporta en producción.
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    pages: int


class PdfExtractor:
    def __init__(self, max_pages: int, min_chars: int, max_chars: int) -> None:
        self._max_pages = max_pages
        self._min_chars = min_chars
        self._max_chars = max_chars

    def extract(self, data: bytes) -> ExtractedPdf:
        # Algunos generadores dejan bytes basura antes de la cabecera; la especificación
        # permite buscarla en los primeros 1024 bytes.
        if PDF_MAGIC not in data[:1024]:
            raise InvalidPdfError("El archivo no es un PDF válido.")

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                # Muchos PDFs "protegidos" solo restringen la impresión y se abren con contraseña vacía.
                if not reader.decrypt(""):
                    raise InvalidPdfError("El PDF está protegido con contraseña.")
            page_count = len(reader.pages)
            if page_count > self._max_pages:
                raise TooManyPagesError(
                    f"El CV tiene {page_count} páginas; el máximo es {self._max_pages}."
                )
            raw = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (InvalidPdfError, TooManyPagesError):
            raise
        except (PdfReadError, PyPdfError, ValueError, KeyError, TypeError) as exc:
            raise InvalidPdfError("PDF corrupto o ilegible.") from exc
        except NotImplementedError as exc:  # p. ej. cifrado AES sin la librería de criptografía
            raise InvalidPdfError("El PDF está protegido con un cifrado no soportado.") from exc

        text = normalize(raw)
        if len(text) < self._min_chars:
            raise PdfNoTextError()

        # Recorte defensivo para no disparar el coste del LLM con PDFs anómalos.
        return ExtractedPdf(text=text[: self._max_chars], pages=page_count)
