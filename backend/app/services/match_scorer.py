"""Puntuación de compatibilidad determinista: la calcula el backend, no el LLM.

Solo puede subir si las keywords de la oferta aparecen en el CV optimizado, y el LLM tiene
prohibido añadir competencias que no estén en el CV original. Se calcula solo con requisitos
verificables (herramientas, titulaciones, idiomas...), nunca con rasgos de personalidad.
"""

import re

from app.schemas.optimize import MatchReport
from app.services.text_utils import STOPWORDS, fold, tokens

# Palabras que aparecen en casi cualquier oferta y CV: como keyword sueltas no miden encaje
# ("experiencia", "Formación"...). Si van acompañadas de contenido sí cuentan
# ("experiencia en contabilidad").
_GENERIC_WORDS = frozenset(
    "experiencia experience formacion education conocimiento conocimientos knowledge ano anos year "
    "years requisito requisitos requirement requirements puesto position empresa company equipo team "
    "perfil profile trabajo work funciones tareas candidato candidata incorporacion valorable "
    "imprescindible minimo minima nivel level capacidad habilidad habilidades".split()
)


def contains(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _is_generic(keyword: str) -> bool:
    words = [t for t in tokens(keyword) if t not in STOPWORDS]
    return all(t.isdigit() or t in _GENERIC_WORDS for t in words)


def clean_keywords(keywords: list[str], job_offer: str, limit: int = 30) -> list[str]:
    """Deduplica y descarta keywords que no aparecen literalmente en la oferta o que son
    genéricas (solo "experiencia", "años", cifras...)."""
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        key = fold(kw)
        if not kw or len(kw) > 60 or key in seen or _is_generic(kw) or not contains(job_offer, kw):
            continue
        seen.add(key)
        result.append(kw)
    return result[:limit]


def clean_soft_skills(
    soft_skills: list[str], job_offer: str, keywords: list[str], limit: int = 15
) -> list[str]:
    """Rasgos personales que pide la oferta. Solo los que aparecen en ella y no son ya keywords."""
    taken = {fold(k) for k in keywords}
    return [s for s in clean_keywords(soft_skills, job_offer, limit=limit) if fold(s) not in taken]


def dropped_keywords(keywords: list[str], original_cv: str, optimized_cv: str) -> list[str]:
    """Keywords de la oferta que el candidato ya tenía en su CV y la optimización ha quitado."""
    return [kw for kw in keywords if contains(original_cv, kw) and not contains(optimized_cv, kw)]


def score(
    keywords: list[str],
    original_cv: str,
    optimized_cv: str,
    exclude: set[str] | frozenset[str] = frozenset(),
    soft_skills: list[str] | None = None,
) -> MatchReport:
    """`exclude`: keywords que el validador detectó como añadidas sin estar en el CV original.
    No cuentan como cubiertas: la puntuación no puede subir a base de inventar."""
    soft = soft_skills or []
    if not keywords:
        return MatchReport(
            score_before=0, score_after=0, matched_keywords=[], missing_keywords=[], soft_skills=soft
        )

    before = sum(contains(original_cv, kw) for kw in keywords)
    matched = [kw for kw in keywords if kw not in exclude and contains(optimized_cv, kw)]
    missing = [kw for kw in keywords if kw not in matched]
    return MatchReport(
        score_before=round(100 * before / len(keywords)),
        score_after=round(100 * len(matched) / len(keywords)),
        matched_keywords=matched,
        missing_keywords=missing,
        soft_skills=soft,
    )
