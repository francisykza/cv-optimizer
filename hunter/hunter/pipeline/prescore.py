"""Pre-score determinista 0–100 (SPEC §6.5): ordena la cola del juez y sirve de desempate.

No es el "score" que ve el usuario: solo mide cuántos términos de su perfil aparecen en la oferta,
con un pequeño extra por modalidad y frescura.
"""

import re
from datetime import date
from pathlib import Path

from app.services.match_scorer import contains
from app.services.text_utils import fold

from hunter.rules.engine import JobFacts
from hunter.rules.schema import GoldenRules

# Con más términos que este número, encontrar estos ya da la cobertura máxima.
_TERMS_FOR_FULL_COVERAGE = 8
_SKILL_HEADING = re.compile(r"habilidad|skill|tecnolog|stack|herramienta|tool|competenc|conocimiento", re.I)
_HEADING = re.compile(r"^\s*#{1,6}\s+(.+)$")
_ITEM_SPLIT = re.compile(r"[,;·•|]|\s+-\s+")


def profile_terms(profile_text: str) -> list[str]:
    """Términos de las secciones de habilidades de `profile.md` (listas o líneas separadas por comas)."""
    terms: list[str] = []
    in_skills = False
    for line in profile_text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            in_skills = bool(_SKILL_HEADING.search(heading.group(1)))
            continue
        if not in_skills:
            continue
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", line)
        line = line.split(":", 1)[-1]  # "Lenguajes: Python, SQL" -> "Python, SQL"
        for item in _ITEM_SPLIT.split(line):
            item = item.strip(" .()")
            if 1 < len(item) <= 40:
                terms.append(item)
    return terms


def load_profile_terms(path: Path) -> list[str]:
    try:
        return profile_terms(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def prescore(facts: JobFacts, rules: GoldenRules, extra_terms: list[str], today: date) -> int:
    seen: set[str] = set()
    terms: list[str] = []
    for term in [*rules.required_any.terms, *extra_terms]:
        key = fold(term)
        if key and key not in seen:
            seen.add(key)
            terms.append(term)

    text = f"{facts.title}\n{facts.description}"
    coverage = 0.0
    if terms:
        hits = sum(contains(text, term) for term in terms)
        coverage = min(1.0, hits / min(len(terms), _TERMS_FOR_FULL_COVERAGE))

    bonus = 0
    if facts.modality == "remote" and rules.location.accept_remote:
        bonus += 10
    elif facts.location_bucket in {*rules.location.onsite_allowed_areas, fold(rules.location.home_area)}:
        bonus += 10
    if facts.date_posted is not None and (today - facts.date_posted).days <= 3:
        bonus += 5
    return max(0, min(100, round(coverage * 85) + bonus))
