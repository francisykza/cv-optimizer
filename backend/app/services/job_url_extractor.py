"""Extrae el texto de una oferta de empleo a partir de su URL con Jina Reader (r.jina.ai).

Jina descarga y renderiza la página por nosotros, así que el backend nunca se conecta a la URL
del usuario (sin riesgo de SSRF hacia la red interna). Pero Jina responde 200 también con muros
de login, banners de cookies o páginas de error (LinkedIn, InfoJobs...): por eso, además del
código HTTP, se comprueba que el texto *parezca* una oferta antes de devolverlo.
"""

import ipaddress
import logging
import re
from urllib.parse import urlsplit

import httpx

from app.core.exceptions import InvalidJobUrlError, JobUrlUnreadableError
from app.services.text_utils import fold

logger = logging.getLogger(__name__)

JINA_READER_URL = "https://r.jina.ai/"
MAX_URL_CHARS = 2048
MAX_OFFER_CHARS = 10_000

# Cabecera que Jina antepone al contenido ("Title:", "URL Source:", "Warning:"...).
_JINA_HEADER = re.compile(
    r"^(Title|URL Source|Published Time|Warning|Markdown Content):.*$", re.IGNORECASE | re.MULTILINE
)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BLANK_LINES = re.compile(r"\n\s*\n(\s*\n)+")
_SPACES = re.compile(r"[ \t ]+")

# Expresiones propias de una oferta (normalizadas sin tildes). Hacen falta varias distintas.
_OFFER_MARKERS = (
    "requisitos", "funciones", "responsabilidades", "ofrecemos", "buscamos", "experiencia",
    "salario", "jornada", "contrato", "incorporacion", "descripcion del puesto", "sobre el puesto",
    "tareas", "formacion", "requirements", "responsibilities", "qualifications", "experience",
    "we offer", "we are looking", "about the role", "job description", "what you will do",
    "what you'll do", "salary", "benefits",
)
# Señales de muro de login, cookies, captcha o error.
_WALL_MARKERS = (
    "inicia sesion", "iniciar sesion", "sign in", "log in to", "join linkedin", "captcha",
    "verify you are human", "access denied", "acceso denegado", "page not found",
    "pagina no encontrada", "we and our partners", "use cookies", "utilizamos cookies",
    "enable javascript", "403 forbidden", "too many requests",
)
_MIN_OFFER_MARKERS = 3


def validate_url(url: str) -> str:
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise InvalidJobUrlError("La URL es demasiado larga.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidJobUrlError()
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise InvalidJobUrlError()
    try:
        if not ipaddress.ip_address(host).is_global:
            raise InvalidJobUrlError()
    except ValueError:
        pass  # es un nombre de dominio, no una IP
    return url


def clean_text(raw: str, limit: int = MAX_OFFER_CHARS) -> str:
    text = _JINA_HEADER.sub("", raw)
    text = _MD_IMAGE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.replace("\r\n", "\n").split("\n")]
    text = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    return text[:limit].rstrip()


def looks_like_job_offer(text: str, min_chars: int) -> bool:
    if len(text) < min_chars:
        return False
    folded = fold(text)
    offer_hits = sum(marker in folded for marker in _OFFER_MARKERS)
    wall_hits = sum(marker in folded for marker in _WALL_MARKERS)
    # Una oferta real puede tener un pie con "cookies" o "Sign in": se exige más contenido de
    # oferta cuanto más huele a muro.
    return offer_hits >= _MIN_OFFER_MARKERS + wall_hits


async def extract_job_offer(
    client: httpx.AsyncClient,
    url: str,
    *,
    min_chars: int,
    timeout_s: float = 8.0,
    api_key: str | None = None,
) -> str:
    url = validate_url(url)
    headers = {"X-Return-Format": "text", "Accept": "text/plain"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = await client.get(JINA_READER_URL + url, headers=headers, timeout=timeout_s)
    except httpx.HTTPError as exc:
        # Solo el tipo de error: nunca la URL completa (puede llevar datos en la query).
        logger.warning("job_url_fetch_failed error=%s", type(exc).__name__)
        raise JobUrlUnreadableError() from exc

    if response.status_code != 200:
        logger.info("job_url_blocked status=%d host=%s", response.status_code, urlsplit(url).hostname)
        raise JobUrlUnreadableError()

    text = clean_text(response.text)
    if not looks_like_job_offer(text, min_chars):
        logger.info("job_url_not_an_offer host=%s chars=%d", urlsplit(url).hostname, len(text))
        raise JobUrlUnreadableError()
    return text
