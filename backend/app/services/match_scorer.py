"""Puntuación de compatibilidad determinista: la calcula el backend, no el LLM.

Solo puede subir si las keywords de la oferta aparecen en el CV optimizado, y el LLM tiene
prohibido añadir competencias que no estén en el CV original.
"""

import re

from app.schemas.optimize import MatchReport


def _contains(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def clean_keywords(keywords: list[str], job_offer: str, limit: int = 30) -> list[str]:
    """Deduplica y descarta keywords que no aparecen literalmente en la oferta."""
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        key = kw.lower()
        if not kw or len(kw) > 60 or key in seen or not _contains(job_offer, kw):
            continue
        seen.add(key)
        result.append(kw)
    return result[:limit]


def score(
    keywords: list[str], original_cv: str, optimized_cv: str, exclude: set[str] | frozenset[str] = frozenset()
) -> MatchReport:
    """`exclude`: keywords que el validador detectó como añadidas sin estar en el CV original.
    No cuentan como cubiertas: la puntuación no puede subir a base de inventar."""
    if not keywords:
        return MatchReport(score_before=0, score_after=0, matched_keywords=[], missing_keywords=[])

    before = sum(_contains(original_cv, kw) for kw in keywords)
    matched = [kw for kw in keywords if kw not in exclude and _contains(optimized_cv, kw)]
    missing = [kw for kw in keywords if kw not in matched]
    return MatchReport(
        score_before=round(100 * before / len(keywords)),
        score_after=round(100 * len(matched) / len(keywords)),
        matched_keywords=matched,
        missing_keywords=missing,
    )
