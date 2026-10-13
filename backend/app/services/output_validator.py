"""Validador anti-alucinación (SDD §7.3): contrasta el CV generado con el CV original.

Es determinista (sin LLM): barato, reproducible y testeable. No bloquea el resultado; marca
lo que no está respaldado por el CV original para que el usuario lo revise (y el orquestador
pide al LLM que lo corrija).

Comprobaciones:
- UNGROUNDED_DATE    años que no aparecen en el CV original.
- UNGROUNDED_METRIC  cifras y porcentajes que no aparecen en el CV original.
- UNGROUNDED_ENTITY  empresas, centros, puestos, nombre, emails y URLs no respaldados.
- UNGROUNDED_SKILL   habilidades listadas que no están en el CV original.
- GAP_LEAKED         keywords de la oferta que el CV original no tenía y el optimizado sí.
- FORMAT             tablas, imágenes, HTML o longitud anómala (no cuenta como alucinación).
- LIMITED_CHECK      el CV se tradujo: se omiten las comprobaciones dependientes del idioma.
"""

import re
from dataclasses import dataclass, field

from app.schemas.optimize import ValidationWarning
from app.services.text_utils import STOPWORDS as _STOPWORDS
from app.services.text_utils import SYNONYMS as _SYNONYMS
from app.services.text_utils import clean_markdown as _clean_markdown
from app.services.text_utils import fold
from app.services.text_utils import stem as _stem
from app.services.text_utils import tokens as _tokens

UNGROUNDED_CODES = frozenset(
    {"UNGROUNDED_DATE", "UNGROUNDED_METRIC", "UNGROUNDED_ENTITY", "UNGROUNDED_SKILL", "GAP_LEAKED"}
)

_ES_HINTS = frozenset("de la el los las y en con para del que experiencia desarrollo".split())
_EN_HINTS = frozenset("the and with for of in to experience development skills".split())

_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# Cifras sueltas: "30%", "3x", "10k", "+4 años". No captura las que van pegadas a letras
# por delante (B2, ES6, S3, Python3), que son versiones o niveles y no métricas.
_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)*)(?!\d)")
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+", re.MULTILINE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)[^\s)>\]]+|\b(?:linkedin\.com|github\.com)/[^\s)>\]]+", re.I)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# No se separa por " en ": forma parte de muchos títulos ("Máster en Inteligencia Artificial").
_ENTITY_SEPARATORS = re.compile(r"\s+[—–\-|·@]\s+|\s*,\s+|\s+at\s+(?=[A-Z])")
_SKILL_SEPARATORS = re.compile(r"\s*(?:,|;|·|\||/|\s+y\s+|\s+and\s+)\s*")
_SKILL_LABEL = re.compile(r"^[^:]{1,40}:\s*")
_PARENS = re.compile(r"\([^)]*\)")

_EXPERIENCE = re.compile(r"experien|trayectoria|employment|work history|empleo", re.I)
_EDUCATION = re.compile(r"formaci|educaci|education|estudios|academ", re.I)
_SKILLS = re.compile(
    r"habilidad|skill|competenc|conocimiento|tecnolog|technical|aptitud|herramienta|idioma|language", re.I
)


def _canonical_number(raw: str) -> str:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):  # separadores de miles: 1.000 / 1,000
        return raw.replace(".", "").replace(",", "")
    value = raw.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def detect_language(text: str) -> str | None:
    words = _tokens(text)
    es = sum(w in _ES_HINTS for w in words)
    en = sum(w in _EN_HINTS for w in words)
    if es + en < 5:
        return None
    if es > en * 1.5:
        return "es"
    if en > es * 1.5:
        return "en"
    return None


class SourceIndex:
    """El CV original preprocesado para búsquedas rápidas."""

    def __init__(self, text: str) -> None:
        self.folded = fold(text)
        self.tokens = set(_tokens(text))
        self.stems = {_stem(t) for t in self.tokens}
        self.years = set(_YEAR.findall(text))
        # Solo cifras sueltas, igual que en el CV generado. Si se aceptaran también los dígitos
        # pegados a letras, el "2" de "B2" respaldaría un "2 años de experiencia" inventado.
        self.numbers = {_canonical_number(n) for n in _NUMBER.findall(text)}

    def contains_phrase(self, phrase: str) -> bool:
        phrase = fold(phrase)
        if not phrase:
            return True
        pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
        return re.search(pattern, self.folded) is not None

    def is_grounded(self, term: str, threshold: float = 0.75) -> bool:
        """¿Está `term` respaldado por el CV? Literal, por sinónimo veraz o por cobertura de tokens."""
        folded = fold(term).strip(" .,:;-")
        if not folded or self.contains_phrase(folded):
            return True
        if any(self.contains_phrase(alt) for alt in _SYNONYMS.get(folded, ())):
            return True
        tokens = [t for t in _tokens(folded) if t not in _STOPWORDS]
        if not tokens:
            return True
        covered = sum(self._token_grounded(t) for t in tokens)
        return covered / len(tokens) >= threshold

    def _token_grounded(self, token: str) -> bool:
        if token in self.tokens or _stem(token) in self.stems:
            return True
        return any(alt in self.tokens or self.contains_phrase(alt) for alt in _SYNONYMS.get(token, ()))


@dataclass
class ValidationReport:
    warnings: list[ValidationWarning] = field(default_factory=list)
    leaked_keywords: set[str] = field(default_factory=set)

    @property
    def ungrounded(self) -> list[ValidationWarning]:
        return [w for w in self.warnings if w.code in UNGROUNDED_CODES]

    @property
    def ungrounded_count(self) -> int:
        return len(self.ungrounded)


@dataclass
class _Section:
    title: str
    lines: list[tuple[int, str]] = field(default_factory=list)  # (nivel de heading o 0, texto)


class OutputValidator:
    def __init__(self, max_warnings: int = 30) -> None:
        self._max_warnings = max_warnings

    def validate(self, markdown: str, source_cv: str, job_keywords: list[str]) -> ValidationReport:
        source = SourceIndex(source_cv)
        report = ValidationReport()
        # Un solo aviso por término no respaldado (p. ej. "Kubernetes" no sale como habilidad
        # Y como requisito filtrado); GAP_LEAKED es el más informativo y sustituye al anterior.
        by_term: dict[str, int] = {}

        def add(code: str, message: str, term: str, line: str | None = None) -> None:
            key = fold(term) if code in UNGROUNDED_CODES else f"{code}:{fold(term)}"
            snippet = _clean_markdown(line)[:160] if line else None
            warning = ValidationWarning(code=code, message=message, term=term, snippet=snippet)
            if key in by_term:
                if code == "GAP_LEAKED":
                    report.warnings[by_term[key]] = warning
                return
            if len(report.warnings) >= self._max_warnings:
                return
            by_term[key] = len(report.warnings)
            report.warnings.append(warning)

        lines = markdown.splitlines()
        translated = self._is_translation(markdown, source_cv)

        self._check_years(lines, source, add)
        self._check_numbers(lines, source, add)
        self._check_contact(lines, source, add)
        if translated:
            add(
                "LIMITED_CHECK",
                "El CV se ha generado en otro idioma: los nombres de puestos y habilidades no se han "
                "podido verificar automáticamente. Revísalos con atención.",
                "idioma",
            )
        else:
            sections = self._sections(lines)
            self._check_entities(sections, source, add)
            self._check_skills(sections, source, add)
        report.leaked_keywords = self._check_gap_leaks(markdown, job_keywords, source, lines, add)
        self._check_format(markdown, source_cv, add)
        return report

    # --- Comprobaciones ---------------------------------------------------------------------

    @staticmethod
    def _check_years(lines, source: SourceIndex, add) -> None:
        for line in lines:
            for year in _YEAR.findall(line):
                if year not in source.years:
                    add("UNGROUNDED_DATE", f"El año {year} no aparece en tu CV original.", year, line)

    @staticmethod
    def _check_numbers(lines, source: SourceIndex, add) -> None:
        for line in lines:
            body = _LIST_MARKER.sub("", line)
            body = _EMAIL.sub(" ", _URL.sub(" ", body))
            for match in _NUMBER.finditer(body):
                raw = match.group(1)
                if _YEAR.fullmatch(raw):
                    continue  # los años se validan aparte
                if _canonical_number(raw) not in source.numbers:
                    suffix = "%" if body[match.end() : match.end() + 2].strip().startswith("%") else ""
                    add(
                        "UNGROUNDED_METRIC",
                        f"La cifra '{raw}{suffix}' no aparece en tu CV original.",
                        raw,
                        line,
                    )

    @staticmethod
    def _check_contact(lines, source: SourceIndex, add) -> None:
        for line in lines:
            for value in _EMAIL.findall(line) + _URL.findall(line):
                value = value.rstrip(".,;")
                if fold(value) not in source.folded:
                    add("UNGROUNDED_ENTITY", f"'{value}' no aparece en tu CV original.", value, line)

    @staticmethod
    def _check_entities(sections: list[_Section], source: SourceIndex, add) -> None:
        for section in sections:
            in_history = bool(_EXPERIENCE.search(section.title) or _EDUCATION.search(section.title))
            for level, line in section.lines:
                text = _clean_markdown(line)
                is_entity_line = level == 1 or (
                    in_history and (level >= 3 or line.lstrip().startswith("**"))
                )
                if not is_entity_line:
                    continue
                text = _EMAIL.sub(" ", _URL.sub(" ", _PARENS.sub(" ", text)))
                for segment in _ENTITY_SEPARATORS.split(text):
                    segment = _YEAR.sub(" ", segment).strip(" .:;-")
                    segment = re.sub(r"\b(?:actualidad|presente|present|now|hoy)\b", "", segment, flags=re.I)
                    segment = segment.strip(" .:;-")
                    if len(segment) < 3 or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", segment):
                        continue
                    if not source.is_grounded(segment):
                        add(
                            "UNGROUNDED_ENTITY",
                            f"'{segment}' no aparece en tu CV original.",
                            segment,
                            line,
                        )

    @staticmethod
    def _check_skills(sections: list[_Section], source: SourceIndex, add) -> None:
        for section in sections:
            if not _SKILLS.search(section.title):
                continue
            for level, line in section.lines:
                if level or line.lstrip().startswith("|"):  # las tablas se avisan como FORMAT
                    continue
                text = _SKILL_LABEL.sub("", _clean_markdown(_LIST_MARKER.sub("", line)))
                for item in _SKILL_SEPARATORS.split(text):
                    item = item.strip(" .:;-")
                    if len(item) < 2 or len(item) > 60:
                        continue
                    if not source.is_grounded(item):
                        add(
                            "UNGROUNDED_SKILL",
                            f"La habilidad '{item}' no aparece en tu CV original.",
                            item,
                            line,
                        )

    @staticmethod
    def _check_gap_leaks(markdown: str, job_keywords: list[str], source: SourceIndex, lines, add) -> set[str]:
        """Keywords de la oferta que el candidato NO tenía y que aun así aparecen en el CV optimizado."""
        optimized = SourceIndex(markdown)
        leaked: set[str] = set()
        for keyword in job_keywords:
            if optimized.contains_phrase(keyword) and not source.is_grounded(keyword, threshold=1.0):
                leaked.add(keyword)
                line = next((ln for ln in lines if fold(keyword) in fold(ln)), None)
                add(
                    "GAP_LEAKED",
                    f"'{keyword}' lo pide la oferta, pero no aparece en tu CV original.",
                    keyword,
                    line,
                )
        return leaked

    @staticmethod
    def _check_format(markdown: str, source_cv: str, add) -> None:
        if re.search(r"^\s*\|.*\|\s*$", markdown, re.MULTILINE):
            add("FORMAT", "El CV contiene tablas, que muchos ATS no leen bien.", "tabla")
        if "![" in markdown:
            add("FORMAT", "El CV contiene imágenes, que los ATS ignoran.", "imagen")
        if re.search(r"<[a-zA-Z/][^>]*>", markdown):
            add("FORMAT", "El CV contiene HTML incrustado.", "html")
        if len(markdown) > len(source_cv) * 1.6 + 400:
            add(
                "FORMAT",
                "El CV optimizado es mucho más largo que el original; revisa que no se haya añadido relleno.",
                "longitud",
            )

    # --- Utilidades ---------------------------------------------------------------------------

    @staticmethod
    def _is_translation(markdown: str, source_cv: str) -> bool:
        a, b = detect_language(markdown), detect_language(source_cv)
        return a is not None and b is not None and a != b

    @staticmethod
    def _sections(lines: list[str]) -> list[_Section]:
        sections = [_Section(title="")]
        for line in lines:
            if not line.strip():
                continue
            heading = _HEADING.match(line)
            if heading:
                level, title = len(heading.group(1)), heading.group(2)
                if level == 2:
                    sections.append(_Section(title=_clean_markdown(title)))
                    continue
                sections[-1].lines.append((level, title))
            else:
                sections[-1].lines.append((0, line))
        return sections
