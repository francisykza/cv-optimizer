"""Años de experiencia exigidos por una oferta (SPEC §6.4), en español e inglés.

Reglas:
- Rangos ("3-5 años") cuentan por su mínimo.
- Con varias menciones se toma el máximo de las obligatorias.
- Lo opcional ("valorable", "nice to have", o una sección "Deseable:") no cuenta.
- Lo que habla de la empresa ("somos una empresa con 15 años de experiencia") no cuenta.
- Sin menciones: None (la regla pasa: ante la duda, no se descarta).
"""

import re
from dataclasses import dataclass

from app.services.text_utils import fold

MAX_PLAUSIBLE_YEARS = 15  # por encima suele ser la antigüedad de la empresa, no un requisito

_NUMBER_WORDS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")(?=\s*(?:\+\s*)?(?:anos?|years?|yrs?)\b)")

_RANGE = r"(?<!\d)(\d{1,2})\s*(?:\+\s*)?(?:(?:-|a|to|o)\s*\d{1,2}\s*)?(?:\+\s*)?"
_PATTERNS = [
    # "3 años de experiencia", "3-5 años de experiencia previa", "+2 años exp."
    re.compile(_RANGE + r"anos?\s+(?:de\s+)?(?:experiencia|exp\b)"),
    # "experiencia (mínima/demostrable) de (al menos) 3 años", "experiencia: 2 años"
    re.compile(
        r"experiencia(?:\s+(?:minima|demostrable|previa|laboral|profesional|comprobable|real))*\s*(?:de|:)?\s*"
        r"(?:al menos\s+|minimo\s+|mas de\s+|un minimo de\s+|entre\s+)?" + _RANGE + r"anos?\b"
    ),
    # "mínimo 3 años", "al menos 2 años", "más de 4 años en..."
    re.compile(r"(?:minimo(?:\s+de)?|al menos|mas de|un minimo de)\s+" + _RANGE + r"anos?\b"),
    # "3+ años" (el "+" es inequívoco)
    re.compile(r"(?<!\d)(\d{1,2})\s*\+\s*anos?\b"),
    # "5+ years", "3-5 years of professional Python experience"
    re.compile(_RANGE + r"(?:years?|yrs?)'?\s+(?:of\s+)?(?:[\w#+./-]+\s+){0,5}?experience"),
    re.compile(r"(?<!\d)(\d{1,2})\s*\+\s*(?:years?|yrs?)\b"),
    # "at least 4 years", "minimum of 3 years"
    re.compile(r"(?:at least|minimum(?:\s+of)?|min\.?|more than|over)\s+" + _RANGE + r"(?:years?|yrs?)\b"),
    # "experience: 3 years"
    re.compile(r"experience\s*(?:of|:)\s*(?:at least\s+)?" + _RANGE + r"(?:years?|yrs?)\b"),
]

_BETWEEN = re.compile(r"\b(?:entre|between)\s+(\d{1,2})\s+(?:y|and)\s+(\d{1,2})\b")
_OPTIONAL = re.compile(
    r"\b(?:valorable|valoraran|se valorara|valoramos|deseable|deseables|un plus|sera un plus|plus|"
    r"nice to have|nice-to-have|preferred|preferable|preferably|bonus|ideally|idealmente|opcional|optional)\b"
)
_COMPANY_CONTEXT = re.compile(
    r"\b(?:empresa|compania|company|somos|we are|we have|nuestra|nuestro|our|llevamos|tenemos|contamos|"
    r"fundada|founded|trayectoria|sector|mercado|market|lideres|leader)\b"
)
_SECTION_WORDS = re.compile(
    r"requisit|requirement|qualification|que buscamos|what we|buscamos|looking for|ofrecemos|we offer|"
    r"responsabilidad|responsibilit|funciones|tareas|perfil|profile|must|imprescindible|deseable|valorable|"
    r"nice to have|bonus|plus|preferred|beneficios|benefits|about|sobre"
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.;!?])\s+")
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦–]|\d+[.)])\s*")


@dataclass(frozen=True)
class ExperienceResult:
    years: int | None
    matched_text: str | None = None


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 70 or re.search(r"\d", stripped):
        return False
    return stripped.endswith(":") or bool(_SECTION_WORDS.search(stripped)) and not stripped.endswith(".")


def _sentences(description: str) -> list[tuple[str, bool]]:
    """(frase plegada, está en una sección opcional)."""
    out: list[tuple[str, bool]] = []
    optional_section = False
    for raw_line in description.splitlines():
        line = fold(_BULLET.sub("", raw_line))
        if not line:
            continue
        # El encabezado puede ir solo en su línea ("Deseable:") o al final de un párrafo
        # ("...conocimientos de Python. Deseable:"): se mira frase a frase.
        for sentence in _SENTENCE_SPLIT.split(line):
            if not sentence:
                continue
            if _is_heading(sentence):
                optional_section = bool(_OPTIONAL.search(sentence))
                continue
            out.append((sentence, optional_section))
    return out


def required_years(description: str) -> ExperienceResult:
    best: tuple[int, str] | None = None
    for sentence, optional_section in _sentences(description):
        if optional_section or _OPTIONAL.search(sentence):
            continue
        sentence = _NUMBER_WORD_RE.sub(lambda m: str(_NUMBER_WORDS[m.group(1)]), sentence)
        sentence = _BETWEEN.sub(r"\1-\2", sentence)  # "entre 2 y 4" -> "2-4" (cuenta el mínimo)
        for pattern in _PATTERNS:
            for match in pattern.finditer(sentence):
                years = int(match.group(1))
                if years == 0 or years > MAX_PLAUSIBLE_YEARS:
                    continue
                if _COMPANY_CONTEXT.search(sentence[: match.start()]):
                    continue
                if best is None or years > best[0]:
                    best = (years, sentence[:200])
    if best is None:
        return ExperienceResult(None)
    return ExperienceResult(best[0], best[1])
