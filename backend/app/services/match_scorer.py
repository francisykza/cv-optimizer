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


# Rasgos personales: el LLM no siempre los separa en `soft_skills` (visto en producción con
# gpt-oss-120b), así que se reclasifican de forma determinista. Prefijos sobre texto normalizado
# (sin tildes) para cubrir género y número: "proactiv" -> proactivo/a/os/as.
_SOFT_PREFIXES = (
    "proactiv", "dinamic", "organizad", "resolutiv", "responsab", "comunicativ", "colabora", "lider",
    "empati", "creativ", "flexib", "adaptab", "iniciativa", "autonom", "polivalen", "motivad", "puntual",
    "orientad", "orientacion", "comprometid", "compromiso", "actitud", "metodic", "meticulos",
    "detallista", "perseveran", "constan", "entusias", "amable", "extrovert", "sociable", "asertiv",
    "proactive", "dynamic", "organized", "organised", "motivated", "teamwork", "leadership",
    "communicat", "reliable", "detail-oriented", "self-starter", "enthusias",
)
_SOFT_PHRASES = frozenset(
    fold(p)
    for p in (
        "trabajo en equipo", "capacidad de trabajo en equipo", "resolución de problemas",
        "atención al detalle", "gestión del tiempo", "pensamiento crítico", "inteligencia emocional",
        "don de gentes", "capacidad de aprendizaje", "ganas de aprender", "buena presencia",
        "habilidades comunicativas", "habilidades sociales", "team player", "problem solving",
        "time management", "critical thinking", "attention to detail", "soft skills",
    )
)


def is_soft_skill(keyword: str) -> bool:
    """¿Es un rasgo personal ("proactiva", "trabajo en equipo") y no un requisito verificable?
    "Responsable de facturación" no lo es: tiene contenido que no es un rasgo."""
    folded = fold(keyword)
    if folded in _SOFT_PHRASES:
        return True
    words = [t for t in tokens(keyword) if t not in STOPWORDS]
    if not words:
        return False
    # "Orientación a resultados", "orientada al cliente": actitudes, sea cual sea el objeto.
    if words[0].startswith("orient"):
        return True
    return all(t.startswith(_SOFT_PREFIXES) for t in words)


def split_soft_skills(keywords: list[str], soft_skills: list[str]) -> tuple[list[str], list[str]]:
    """Separa los rasgos personales que el LLM haya dejado entre las keywords."""
    hard = [k for k in keywords if not is_soft_skill(k)]
    soft = list(soft_skills) + [k for k in keywords if is_soft_skill(k)]
    return hard, soft


def contains(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _is_generic(keyword: str) -> bool:
    words = [t for t in tokens(keyword) if t not in STOPWORDS]
    return all(t.isdigit() or t in _GENERIC_WORDS for t in words)


def clean_keywords(
    keywords: list[str], job_offer: str, limit: int = 30, drop_generic: bool = True
) -> list[str]:
    """Deduplica y descarta keywords que no aparecen literalmente en la oferta o que son
    genéricas (solo "experiencia", "años", cifras...)."""
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        key = fold(kw)
        if not kw or len(kw) > 60 or key in seen or not contains(job_offer, kw):
            continue
        if drop_generic and _is_generic(kw):
            continue
        seen.add(key)
        result.append(kw)
    return result[:limit]


def clean_soft_skills(
    soft_skills: list[str], job_offer: str, keywords: list[str], limit: int = 15
) -> list[str]:
    """Rasgos personales que pide la oferta. Solo los que aparecen en ella y no son ya keywords."""
    taken = {fold(k) for k in keywords}
    cleaned = clean_keywords(soft_skills, job_offer, limit=limit, drop_generic=False)
    return [s for s in cleaned if fold(s) not in taken]


def dropped_keywords(keywords: list[str], original_cv: str, optimized_cv: str) -> list[str]:
    """Keywords de la oferta que el candidato ya tenía en su CV y la optimización ha quitado."""
    return [kw for kw in keywords if contains(original_cv, kw) and not contains(optimized_cv, kw)]


def ats_suggestions(
    match: MatchReport, original_cv: str, optimized_cv: str, limit: int = 6
) -> list[str]:
    """Requisitos verificables de la oferta que faltan y que el candidato no tenía en su CV
    original. Nunca rasgos personales: `missing_keywords` ya los excluye."""
    return [
        kw
        for kw in match.missing_keywords
        if not contains(original_cv, kw) and not contains(optimized_cv, kw)
    ][:limit]


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
