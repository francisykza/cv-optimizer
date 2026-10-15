"""Guillotina determinista (SPEC §5.2): 0 tokens, explicable y "ante la duda, pasa".

Las reglas se evalúan de la más barata a la más cara. En modo normal se corta en la primera que
descarta; en modo explicación (simulación) se devuelven todas las que dispararían.
"""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from app.services.text_utils import fold

from hunter.models import GuillotineResult, Language, Modality, NormalizedJob, RuleHit
from hunter.pipeline.experience import required_years
from hunter.pipeline.normalize import normalize_company
from hunter.rules.schema import GoldenRules

SNIPPET_RADIUS = 70


@dataclass(frozen=True)
class JobFacts:
    """Lo que la guillotina necesita de una oferta (se construye desde la normalización o desde la BD)."""

    title: str
    company_norm: str
    location_bucket: str
    modality: Modality
    language: Language
    description: str
    date_posted: date | None = None
    salary_annual_max: float | None = None
    salary_currency: str | None = None
    location: str = ""

    @classmethod
    def from_normalized(cls, job: NormalizedJob) -> "JobFacts":
        return cls(
            title=job.raw.title,
            company_norm=job.company_norm,
            location_bucket=job.location_bucket,
            modality=job.modality,
            language=job.language,
            description=job.description,
            date_posted=job.raw.date_posted,
            salary_annual_max=job.salary_annual_max,
            salary_currency=job.raw.salary_currency,
            location=job.raw.location,
        )


# --- Ámbito del remoto ---------------------------------------------------------------------

# Lugar mencionado -> ámbito comparable con `location.remote_scopes`.
_PLACES = {
    "spain": "spain",
    "espana": "spain",
    "europe": "europe",
    "europa": "europe",
    "eu": "europe",
    "european union": "europe",
    "union europea": "europe",
    "cet": "europe",
    "cest": "europe",
    "emea": "emea",
    "worldwide": "worldwide",
    "anywhere": "worldwide",
    "cualquier lugar": "worldwide",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "estados unidos": "us",
    "america": "us",
    "uk": "uk",
    "united kingdom": "uk",
    "reino unido": "uk",
    "england": "uk",
    "canada": "canada",
    "germany": "germany",
    "alemania": "germany",
    "deutschland": "germany",
    "france": "france",
    "francia": "france",
    "netherlands": "netherlands",
    "the netherlands": "netherlands",
    "holland": "netherlands",
    "portugal": "portugal",
    "poland": "poland",
    "polonia": "poland",
    "ireland": "ireland",
    "irlanda": "ireland",
    "italy": "italy",
    "italia": "italy",
    "india": "india",
    "latam": "latam",
    "latin america": "latam",
    "latinoamerica": "latam",
    "north america": "north america",
    "americas": "americas",
    "brazil": "brazil",
    "brasil": "brazil",
    "mexico": "mexico",
    "argentina": "argentina",
    "colombia": "colombia",
    "chile": "chile",
    "australia": "australia",
    "switzerland": "switzerland",
    "suiza": "switzerland",
    "austria": "austria",
    "sweden": "sweden",
    "denmark": "denmark",
    "norway": "norway",
    "finland": "finland",
    "belgium": "belgium",
    "romania": "romania",
    "ukraine": "ukraine",
    "philippines": "philippines",
    "israel": "israel",
    "singapore": "singapore",
    "japan": "japan",
    "pst": "us",
    "est": "us",
    "us time zones": "us",
}
_PLACE_ALT = "|".join(sorted((re.escape(p) for p in _PLACES), key=len, reverse=True))
_PLACE_CAPTURE = rf"(?:the\s+)?(?P<p>{_PLACE_ALT})\b"
_SCOPE_PATTERNS = [
    re.compile(rf"\b(?P<p>{_PLACE_ALT})[\s-]*only\b"),
    re.compile(
        r"\b(?:only|solo|unicamente|exclusivamente)\s+(?:open\s+to\s+)?(?:candidates|applicants|people|"
        r"candidatos|personas|residents|residentes)?\s*(?:who\s+are\s+)?(?:based|located|residing|living|"
        r"residentes)?\s*(?:in|from|en|de|within)\s+" + _PLACE_CAPTURE
    ),
    re.compile(
        r"\b(?:must|need\s+to|should|have\s+to|debes|debe|deberas|es\s+necesario)\s+(?:be\s+)?(?:based|located|"
        r"reside|residing|living|live|vivir|residir|estar)\s+(?:in|en)\s+" + _PLACE_CAPTURE
    ),
    re.compile(
        r"\b(?:remote|remotely|remoto|teletrabajo)\s+(?:within|from|desde|only\s+in)\s+" + _PLACE_CAPTURE
    ),
    re.compile(
        # "authorized/eligible to work in", "authorization to work in" (visto en una oferta real),
        # "right to work in", "permiso de trabajo en"
        r"\b(?:authorized|authorised|authorization|authorisation|eligible|eligibility|right|permit|permiso)\s+"
        r"(?:to\s+work|de\s+trabajo|para\s+trabajar)\s+(?:in|en)\s+" + _PLACE_CAPTURE
    ),
    re.compile(r"\bwork\s+(?:authorization|authorisation|permit)\s+(?:in|for)\s+" + _PLACE_CAPTURE),
]


@dataclass(frozen=True)
class _Compiled:
    rules: GoldenRules
    companies: tuple[re.Pattern[str], ...]
    seniority: re.Pattern[str] | None
    title_terms: re.Pattern[str] | None
    intermediary: re.Pattern[str] | None
    desc_terms: re.Pattern[str] | None
    required: tuple[tuple[str, re.Pattern[str]], ...]
    allowed_areas: frozenset[str]
    remote_scopes: frozenset[str]
    home_countries: frozenset[str]


def _term_pattern(term: str) -> str:
    folded = fold(term)
    return rf"(?<!\w){re.escape(folded)}(?!\w)"


def _alternation(terms: list[str]) -> re.Pattern[str] | None:
    parts = [_term_pattern(t) for t in terms if fold(t)]
    return re.compile("|".join(parts)) if parts else None


@lru_cache(maxsize=16)
def _compile(rules_json: str) -> _Compiled:
    rules = GoldenRules.model_validate_json(rules_json)
    companies = tuple(
        re.compile(_term_pattern(normalize_company(c) or c)) for c in rules.blacklists.companies if fold(c)
    )
    return _Compiled(
        rules=rules,
        companies=companies,
        seniority=_alternation(rules.seniority.exclude_title_terms),
        title_terms=_alternation(rules.blacklists.title_terms),
        intermediary=_alternation(rules.blacklists.intermediary_signals),
        desc_terms=_alternation(rules.blacklists.description_terms),
        required=tuple((t, re.compile(_term_pattern(t))) for t in rules.required_any.terms if fold(t)),
        allowed_areas=frozenset({*rules.location.onsite_allowed_areas, fold(rules.location.home_area)}),
        remote_scopes=frozenset(rules.location.remote_scopes),
        home_countries=frozenset(_PLACES.get(c, c) for c in rules.location.home_countries),
    )


# Ámbitos que no son un país: en una ubicación no dicen dónde está la oficina.
_NOT_COUNTRIES = frozenset({"europe", "emea", "worldwide", "latam", "north america", "americas"})
# Estados de EE. UU. abreviados ("Knoxville, TN"), por si la ubicación no termina en "USA".
_US_STATE = re.compile(
    r"^(?:al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|"
    r"ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc)$"
)


def _location_country(location: str) -> str | None:
    """País de una ubicación de portal ("Knoxville, TN, USA" -> "us"), o None si no se reconoce."""
    parts = [p.strip(" .()") for p in re.split(r"[,;/|]", fold(location)) if p.strip(" .()")]
    for part in reversed(parts):
        country = _PLACES.get(part)
        if country:
            return None if country in _NOT_COUNTRIES else country
    if len(parts) >= 2 and _US_STATE.match(parts[-1]):
        return "us"
    return None


def _snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(text), match.end() + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return (prefix + text[start:end].replace("\n", " ") + suffix)[:200]


def _title_text(title: str) -> str:
    return re.sub(r"[^\w+#]+", " ", fold(title)).strip()


class _Evaluator:
    def __init__(self, facts: JobFacts, compiled: _Compiled, today: date) -> None:
        self.f = facts
        self.c = compiled
        self.r = compiled.rules
        self.today = today
        self._desc: str | None = None

    @property
    def desc(self) -> str:
        if self._desc is None:
            self._desc = fold(self.f.description)
        return self._desc

    def bl_company(self) -> RuleHit | None:
        for pattern in self.c.companies:
            if pattern.search(self.f.company_norm):
                return RuleHit(
                    rule_id="BL_COMPANY",
                    rule_label="Empresa en tu lista negra",
                    matched_text=self.f.company_norm[:200],
                )
        return None

    def stale(self) -> RuleHit | None:
        max_age = self.r.freshness.max_age_days
        if max_age is None or self.f.date_posted is None:
            return None
        age = (self.today - self.f.date_posted).days
        if age > max_age:
            return RuleHit(
                rule_id="STALE",
                rule_label=f"Publicada hace {age} días (máximo {max_age})",
                matched_text=self.f.date_posted.isoformat(),
            )
        return None

    def _title_rule(self, pattern: re.Pattern[str] | None, rule_id: str, label: str) -> RuleHit | None:
        if pattern is None:
            return None
        title = _title_text(self.f.title)
        match = pattern.search(title)
        if match:
            return RuleHit(
                rule_id=rule_id, rule_label=f"{label}: «{match.group(0)}»", matched_text=self.f.title[:200]
            )
        return None

    def sen_title(self) -> RuleHit | None:
        return self._title_rule(self.c.seniority, "SEN_TITLE", "Nivel excluido en el título")

    def bl_title_term(self) -> RuleHit | None:
        return self._title_rule(self.c.title_terms, "BL_TITLE_TERM", "Término excluido en el título")

    def loc_onsite_out_of_area(self) -> RuleHit | None:
        bucket = self.f.location_bucket
        if bucket in ("unknown", "remote") or bucket in self.c.allowed_areas:
            return None
        modality = self.f.modality
        if modality == "onsite" or (modality == "hybrid" and not self.r.location.accept_hybrid_outside_area):
            kind = "Presencial" if modality == "onsite" else "Híbrido"
            return RuleHit(
                rule_id="LOC_ONSITE_OUT_OF_AREA",
                rule_label=f"{kind} fuera de tu zona ({bucket})",
                matched_text=bucket,
            )
        return None

    def loc_foreign_country(self) -> RuleHit | None:
        """Ubicación en otro país sin que la oferta diga que es remota. Sin modalidad no es "duda":
        un puesto en "Knoxville, TN, USA" no es para alguien de Málaga aunque no diga "presencial"."""
        if self.f.modality == "remote":
            return None
        country = _location_country(self.f.location)
        if country is None or country in self.c.home_countries:
            return None
        return RuleHit(
            rule_id="LOC_FOREIGN_COUNTRY",
            rule_label=f"En otro país sin indicar que sea remoto ({country})",
            matched_text=self.f.location[:200],
        )

    def loc_remote_scope(self) -> RuleHit | None:
        if self.f.modality != "remote":
            return None
        if not self.r.location.accept_remote:
            return RuleHit(rule_id="LOC_REMOTE_SCOPE", rule_label="Es remoto y no aceptas remoto")
        text = f"{fold(self.f.location)}\n{self.desc}"
        for pattern in _SCOPE_PATTERNS:
            for match in pattern.finditer(text):
                scope = _PLACES.get(match.group("p"))
                if scope and scope not in self.c.remote_scopes:
                    return RuleHit(
                        rule_id="LOC_REMOTE_SCOPE",
                        rule_label=f"Remoto restringido a un ámbito que no aceptas ({scope})",
                        matched_text=_snippet(text, match),
                    )
        return None

    def lang_not_allowed(self) -> RuleHit | None:
        lang = self.f.language
        if lang == "unknown" or lang in self.r.languages.allowed:
            return None
        return RuleHit(rule_id="LANG_NOT_ALLOWED", rule_label=f"Idioma de la oferta no aceptado ({lang})")

    def exp_too_many_years(self) -> RuleHit | None:
        max_years = self.r.experience.max_years_required
        if max_years is None:
            return None
        result = required_years(self.f.description)
        if result.years is not None and result.years > max_years:
            return RuleHit(
                rule_id="EXP_TOO_MANY_YEARS",
                rule_label=f"Pide {result.years} años (máximo {max_years})",
                matched_text=result.matched_text,
            )
        return None

    def _desc_rule(self, pattern: re.Pattern[str] | None, rule_id: str, label: str) -> RuleHit | None:
        if pattern is None:
            return None
        match = pattern.search(self.desc)
        if match:
            return RuleHit(
                rule_id=rule_id,
                rule_label=f"{label}: «{match.group(0)}»",
                matched_text=_snippet(self.desc, match),
            )
        return None

    def bl_intermediary(self) -> RuleHit | None:
        return self._desc_rule(self.c.intermediary, "BL_INTERMEDIARY", "Parece una intermediaria")

    def bl_desc_term(self) -> RuleHit | None:
        return self._desc_rule(self.c.desc_terms, "BL_DESC_TERM", "Término excluyente en la descripción")

    def sal_below_min(self) -> RuleHit | None:
        minimum = self.r.salary.min_annual_eur
        salary = self.f.salary_annual_max
        if minimum is None or salary is None:
            return None
        if (self.f.salary_currency or "EUR").upper() != "EUR":
            return None  # sin conversión de moneda: ante la duda, pasa
        if salary < minimum:
            return RuleHit(
                rule_id="SAL_BELOW_MIN",
                rule_label=f"Salario máximo {salary:,.0f} € (mínimo {minimum:,.0f} €)".replace(",", "."),
            )
        return None

    def req_any_missing(self) -> RuleHit | None:
        needed = self.r.required_any.min_hits
        if not self.c.required or needed <= 0:
            return None
        haystack = f"{_title_text(self.f.title)}\n{self.desc}"
        hits = [term for term, pattern in self.c.required if pattern.search(haystack)]
        if len(hits) < needed:
            return RuleHit(
                rule_id="REQ_ANY_MISSING",
                rule_label=f"Solo {len(hits)} de {needed} términos imprescindibles",
                matched_text=", ".join(hits)[:200] or None,
            )
        return None

    ORDER = (
        "bl_company",
        "stale",
        "sen_title",
        "bl_title_term",
        "loc_onsite_out_of_area",
        "loc_foreign_country",
        "loc_remote_scope",
        "lang_not_allowed",
        "exp_too_many_years",
        "bl_intermediary",
        "bl_desc_term",
        "sal_below_min",
        "req_any_missing",
    )

    def run(self, explain: bool) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for name in self.ORDER:
            hit = getattr(self, name)()
            if hit is not None:
                hits.append(hit)
                if not explain:
                    break
        return hits


def evaluate(facts: JobFacts, rules: GoldenRules, today: date, explain: bool = False) -> list[RuleHit]:
    """Reglas que descartan la oferta (vacío = pasa)."""
    return _Evaluator(facts, _compile(rules.canonical_json()), today).run(explain)


def guillotine(facts: JobFacts, rules: GoldenRules, today: date) -> GuillotineResult:
    hits = evaluate(facts, rules, today)
    if not hits:
        return GuillotineResult(passed=True, rules_version=rules.version)
    hit = hits[0]
    return GuillotineResult(
        passed=False,
        rule_id=hit.rule_id,
        rule_label=hit.rule_label,
        matched_text=hit.matched_text,
        rules_version=rules.version,
    )
