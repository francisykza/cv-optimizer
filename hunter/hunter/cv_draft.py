"""Borrador del perfil a partir del CV en PDF (SPEC §19.4): sin IA, sin tokens y sin salir del equipo.

Reutiliza el extractor del backend (pypdf, todo en memoria) y reparte el texto del CV en los apartados del
perfil reconociendo sus títulos ("EXPERIENCIA PROFESIONAL", "Skills"...). No redacta nada: copia lo que dice
el CV (ADR-010: ningún dato inventado) y deja fuera el nombre y los datos de contacto, porque el perfil viaja
a Groq con cada oferta. Si no cabe en lo que lee el juez, recorta primero lo más largo.
"""

import asyncio
import re
from dataclasses import dataclass, field

from app.core.exceptions import InvalidPdfError
from app.services.pdf_extractor import PdfExtractor
from app.services.text_utils import fold
from starlette.concurrency import run_in_threadpool

from hunter.judge.judge import PROFILE_MAX_CHARS

# Mismos límites que el Optimizador (backend/app/core/config.py).
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 5
EXTRACTION_TIMEOUT_S = 10.0
# Hueco que queda libre para que el usuario añada qué busca (el CV no lo dice).
BUDGET = PROFILE_MAX_CHARS - 300
MAX_ITEM_CHARS = 300

_EXTRACTOR = PdfExtractor(max_pages=MAX_PDF_PAGES, min_chars=200, max_chars=30_000)

# Apartado → (título en el perfil, títulos con los que suele aparecer en un CV, sin tildes ni mayúsculas).
# Los títulos del perfil son los que reconoce el pre-score: "Habilidades técnicas" sí, "Cualidades" no.
_SECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "summary": (
        "Resumen",
        (
            "perfil", "perfil profesional", "resumen", "resumen profesional", "sobre mi", "acerca de mi",
            "extracto", "objetivo", "objetivo profesional", "presentacion", "about me", "summary",
            "professional summary", "profile", "objective",
        ),
    ),
    "skills": (
        "Habilidades técnicas",
        (
            "habilidades", "habilidades tecnicas", "competencias", "competencias tecnicas", "conocimientos",
            "conocimientos tecnicos", "conocimientos informaticos", "aptitudes", "tecnologias",
            "herramientas", "stack", "stack tecnologico", "informatica", "skills", "technical skills",
            "hard skills", "tech stack", "tools", "technologies",
        ),
    ),
    "soft": (
        "Cualidades",
        (
            "soft skills", "habilidades blandas", "habilidades personales", "habilidades sociales",
            "competencias personales", "competencias transversales",
        ),
    ),
    "languages": ("Idiomas", ("idiomas", "lenguas", "languages")),
    "experience": (
        "Experiencia relevante",
        (
            "experiencia", "experiencia laboral", "experiencia profesional", "trayectoria",
            "trayectoria profesional", "historial laboral", "experience", "work experience",
            "professional experience", "employment", "employment history",
        ),
    ),
    "projects": (
        "Proyectos",
        (
            "proyectos", "proyectos personales", "proyectos destacados", "portfolio", "projects",
            "personal projects", "side projects",
        ),
    ),
    "education": (
        "Formación",
        (
            "formacion", "formacion academica", "educacion", "estudios", "titulacion", "titulaciones",
            "cursos", "certificaciones", "certificados", "formacion complementaria", "education",
            "courses", "certifications", "licencias y certificaciones",
        ),
    ),
    # Se descartan enteros: no ayudan al juez y algunos son datos personales.
    "skip": (
        "",
        (
            "datos personales", "contacto", "informacion de contacto", "informacion personal",
            "referencias", "intereses", "aficiones", "hobbies", "otros datos", "contact",
            "personal details", "personal information", "references", "interests",
        ),
    ),
}
_ORDER = ("summary", "skills", "soft", "languages", "experience", "projects", "education")
_CONNECTORS = ("y", "e", "and", "&")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Con esquema o "www.", o un dominio seguido de ruta ("linkedin.com/in/..."). Sin ruta no: "ASP.NET",
# "Socket.io" o "Node.js" son tecnologías.
_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:[\w-]+\.)+[a-z]{2,6}/\S*", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:(?:\+|00)\d{2,3}[\s.-]?)?[6-9](?:[\s.-]?\d){8}(?!\d)|(?<!\d)(?:\+|00)\d[\d\s.-]{7,}\d(?!\d)"
)
# Líneas de contacto con etiqueta ("Teléfono: ...", "LinkedIn: ...") y pies de página del PDF. Sin los dos
# puntos no: "GitHub Actions" es una herramienta.
_CONTACT_LINE = re.compile(
    r"^(?:(?:tel[eé]fono|tel|m[oó]vil|e-?mail|correo(?: electr[oó]nico)?|direcci[oó]n|domicilio|linkedin|"
    r"github|web|dni|nie|fecha de nacimiento)\s*:|(?:p[aá]gina|page) \d+(?: (?:de|of) \d+)?$)",
    re.IGNORECASE,
)
_MONTHS = (
    r"ene(?:ro)?|feb(?:rero|ruary)?|mar(?:zo|ch)?|abr(?:il)?|apr(?:il)?|may(?:o)?|jun(?:io|e)?|"
    r"jul(?:io|y)?|ago(?:sto)?|aug(?:ust)?|sep(?:t(?:iembre|ember)?)?|oct(?:ubre|ober)?|"
    r"nov(?:iembre|ember)?|dic(?:iembre)?|dec(?:ember)?|jan(?:uary)?"
)
_DATE_ONLY = re.compile(
    rf"^(?:\b(?:{_MONTHS})\b\.?|\d{{1,4}}|actualidad|presente|actual|hoy|present|now|current|de|a|hasta|to|"
    r"[/\-–—.,()\s])+$",
    re.IGNORECASE,
)


@dataclass
class Draft:
    text: str
    sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def extract_text(data: bytes) -> str:
    """Texto del PDF con el extractor del Optimizador. Errores del backend: INVALID_PDF, PDF_NO_TEXT,
    TOO_MANY_PAGES."""
    try:
        extracted = await asyncio.wait_for(
            run_in_threadpool(_EXTRACTOR.extract, data), timeout=EXTRACTION_TIMEOUT_S
        )
    except TimeoutError as exc:
        raise InvalidPdfError("El PDF es demasiado complejo para procesarlo.") from exc
    return extracted.text


def section_of(line: str) -> str | None:
    """Apartado que abre esta línea si es un título ("EXPERIENCIA PROFESIONAL", "Skills & tools:")."""
    raw = line.strip()
    if not raw or len(raw) > 48 or raw[-1] in ".,;":
        return None
    key = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", " ", fold(raw))).strip()
    if not key:
        return None
    shouting = raw.upper() == raw and any(c.isalpha() for c in raw)
    best: tuple[int, str] | None = None
    for kind, (_, names) in _SECTIONS.items():
        for name in names:
            if key == name:
                matched = True
            elif key.startswith(name + " ") and len(key.split()) <= 5:
                rest = key[len(name) + 1 :]
                matched = shouting or rest.split()[0] in _CONNECTORS
            else:
                matched = False
            if matched and (best is None or len(name) > best[0]):
                best = (len(name), kind)
    return best[1] if best else None


def _scrub(line: str) -> tuple[str, bool]:
    """Quita correos, teléfonos y enlaces (conserva la viñeta). Devuelve la línea y si quitó algo."""
    text = line.strip()
    bullet = text.startswith("- ")
    if bullet:
        text = text[2:].strip()
    if _CONTACT_LINE.match(text):
        return "", True
    removed = 0
    for pattern in (_EMAIL, _URL, _PHONE):
        text, n = pattern.subn("", text)
        removed += n
    if removed:
        text = re.sub(r"\s{2,}", " ", text).strip(" |·•,;:-")
    if not text:
        return "", bool(removed)
    return (f"- {text}" if bullet else text), bool(removed)


def _items(lines: list[str]) -> list[str]:
    """Líneas del CV → elementos de lista: une las que el PDF partió y pega las fechas al puesto."""
    items: list[str] = []
    for line in lines:
        bullet = line.startswith("- ")
        text = line[2:].strip() if bullet else line.strip()
        if not text:
            continue
        if items and not bullet and any(c.isdigit() for c in text) and _DATE_ONLY.match(text):
            items[-1] = f"{items[-1]} ({text})"
        elif items and not bullet and text[0].islower():
            items[-1] = f"{items[-1]} {text}"
        else:
            items.append(text)
    return [_clip(item) for item in items]


def _clip(item: str) -> str:
    return item if len(item) <= MAX_ITEM_CHARS else item[: MAX_ITEM_CHARS - 1].rstrip() + "…"


def _sentences(lines: list[str]) -> list[str]:
    paragraph = " ".join(line.lstrip("- ").strip() for line in lines if line.strip())
    return [s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s]


def _render(parts: dict[str, list[str]]) -> str:
    blocks = []
    for kind in _ORDER:
        if parts.get(kind):
            title = _SECTIONS[kind][0]
            body = " ".join(parts[kind]) if kind == "summary" else "\n".join(f"- {i}" for i in parts[kind])
            blocks.append(f"## {title}\n{body}")
    return "\n\n".join(blocks) + "\n"


def build(cv_text: str) -> Draft:
    """Reparte el texto del CV en los apartados del perfil. Lo que hay antes del primer título (nombre,
    puesto y contacto) se queda fuera."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    header = 0
    scrubbed = False
    for line in cv_text.splitlines():
        kind = section_of(line)
        if kind is not None:
            current = kind
            found.setdefault(kind, [])
            continue
        if current is None:
            header += bool(line.strip())
            continue
        if current == "skip":
            continue
        clean, removed = _scrub(line)
        scrubbed |= removed
        if clean:
            found[current].append(clean)

    if not any(found.get(kind) for kind in _ORDER):
        return _fallback(cv_text)

    parts = {
        kind: (_sentences(found[kind]) if kind == "summary" else _items(found[kind]))
        for kind in _ORDER
        if found.get(kind)
    }
    trimmed = _fit(parts)
    draft = Draft(_render(parts), sections=[_SECTIONS[k][0] for k in _ORDER if parts.get(k)])
    if header:
        draft.warnings.append(
            "He dejado fuera la cabecera del CV (tu nombre y tus datos de contacto): el perfil viaja a Groq "
            "con cada oferta."
        )
    if scrubbed:
        draft.warnings.append("He quitado correos, teléfonos y enlaces.")
    if trimmed:
        names = ", ".join(_SECTIONS[k][0] for k in _ORDER if k in trimmed)
        draft.warnings.append(f"He recortado {names}: el juez lee como mucho {PROFILE_MAX_CHARS} caracteres.")
    if "skills" not in parts:
        draft.warnings.append(
            "No he encontrado un apartado de habilidades: añádelo, porque el pre-score busca ahí tus "
            "tecnologías."
        )
    draft.warnings.append(
        "Añade al resumen qué puesto buscas: el CV no lo dice. Tus prioridades de las Reglas de Oro ya le "
        "llegan al juez aparte."
    )
    return draft


def _fit(parts: dict[str, list[str]]) -> set[str]:
    """Quita líneas del final del apartado más largo hasta que el perfil cabe. Devuelve los recortados."""
    trimmed: set[str] = set()
    while len(_render(parts)) > BUDGET:
        candidates = [k for k in parts if len(parts[k]) > 1]
        if not candidates:
            longest = max(parts, key=lambda k: len(" ".join(parts[k])))
            excess = len(_render(parts)) - BUDGET
            parts[longest][-1] = parts[longest][-1][: max(20, len(parts[longest][-1]) - excess - 1)] + "…"
            trimmed.add(longest)
            break
        kind = max(candidates, key=lambda k: len(" ".join(parts[k])))
        parts[kind].pop()
        trimmed.add(kind)
    return trimmed


def _fallback(cv_text: str) -> Draft:
    """CV sin títulos reconocibles: el texto tal cual (sin contactos), para ordenarlo a mano."""
    lines = []
    for line in cv_text.splitlines():
        clean, _ = _scrub(line)
        if clean:
            lines.append(clean)
    body = "\n".join(lines)
    if len(body) > BUDGET:
        body = body[: body.rfind("\n", 0, BUDGET) if "\n" in body[:BUDGET] else BUDGET].rstrip()
    return Draft(
        f"## Mi CV (sin ordenar)\n{body}\n",
        sections=["Mi CV (sin ordenar)"],
        warnings=[
            "No he reconocido los apartados de tu CV: ponle títulos como «Habilidades técnicas» o "
            "«Experiencia relevante» y quita tu nombre si aparece.",
            "He quitado correos, teléfonos y enlaces.",
        ],
    )
