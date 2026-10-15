"""Normalización de ofertas (SPEC §6.2): texto limpio, claves comparables, ubicación y modalidad."""

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.consent_filter import strip_consent_noise
from app.services.output_validator import detect_language
from app.services.text_utils import clean_markdown, fold

from hunter.models import Language, Modality, NormalizedJob, RawJob
from hunter.pipeline.dedup import desc_fingerprint_text, job_key, sha256_hex, simhash_hex

# --- Descripción ---------------------------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]+>")
_BLOCK_TAG = re.compile(r"<\s*(?:br|/p|/li|/h\d|/div|/tr)\s*/?>", re.I)
_SPACES = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# Restos de Markdown que clean_markdown no quita: escapes ("\-", "\*") y viñetas.
_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|])")


def clean_description(text: str) -> str:
    """Texto plano legible: sin HTML, sin Markdown, sin banners de cookies y con párrafos."""
    if not text:
        return ""
    if "<" in text and _HTML_TAG.search(text):
        text = _BLOCK_TAG.sub("\n", text)
        text = _HTML_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _MD_ESCAPE.sub(r"\1", text)
    text = clean_markdown(text)
    text = strip_consent_noise(text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


# --- Empresa y título ----------------------------------------------------------------------

_COMPANY_SUFFIXES = re.compile(
    r"(?:,?\s+|^)(?:s\.?\s?l\.?\s?u\.?|s\.?\s?l\.?|s\.?\s?a\.?\s?u\.?|s\.?\s?a\.?|s\.?\s?c\.?|s\.?\s?coop\.?|"
    r"inc\.?|ltd\.?|llc|gmbh|ag|plc|bv|b\.v\.|corp\.?|corporation|limited|group|grupo|holding)$"
)
_PUNCT = re.compile(r"[^\w\s&+#]")


def normalize_company(company: str) -> str:
    value = fold(company)
    # Varias pasadas: "Acme Group S.L." -> "acme group" -> "acme".
    for _ in range(3):
        stripped = _COMPANY_SUFFIXES.sub("", value).strip(" ,.-")
        if stripped == value or not stripped:
            break
        value = stripped
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", value)).strip()


# "(m/f/d)", "(h/m)", "(f/m/x)", "(m/w/d)", "(he/him)"...
_GENDER_MARK = re.compile(r"\(\s*[a-z]{1,3}\s*(?:/\s*[a-z]{1,3}\s*){1,3}\)")
_TITLE_PREFIX = re.compile(
    r"^(?:oferta(?: de empleo)?|empleo|vacante|job|hiring|we are hiring|se busca)\s*[:\-]\s*"
)
_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def normalize_title(title: str) -> str:
    """Comparable entre portales. El nivel (junior/senior) se conserva."""
    value = fold(title)
    value = _GENDER_MARK.sub(" ", value)
    value = _TITLE_PREFIX.sub("", value)
    value = _PARENS.sub(" ", value)  # suele ser ubicación o modalidad: "(Remoto)", "[Málaga]"
    value = re.split(r"\s+[|]\s+|\s+-\s+(?=remot|hibrid|hybrid|presencial|on-?site)", value)[0]
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", value)).strip()


# --- Ubicación -----------------------------------------------------------------------------

_REMOTE_WORDS = re.compile(r"\b(?:remote|remoto|remota|teletrabajo|anywhere|work from home|home office)\b")
# Nombres que no identifican una ciudad: con solo esto la ubicación es "unknown" (ante la duda, pasa).
_NON_CITY = frozenset(
    fold(x)
    for x in (
        "españa",
        "spain",
        "es",
        "andalucía",
        "andalusia",
        "europe",
        "europa",
        "eu",
        "emea",
        "worldwide",
        "global",
        "comunidad de madrid",
        "community of madrid",
        "cataluña",
        "catalonia",
        "comunidad valenciana",
        "valencian community",
        "país vasco",
        "basque country",
        "galicia",
        "castilla y león",
        "castilla-la mancha",
        "aragón",
        "murcia",
        "región de murcia",
        "canarias",
        "islas baleares",
        "baleares",
        "asturias",
        "cantabria",
        "navarra",
        "la rioja",
        "extremadura",
        "provincia de málaga",
        "málaga province",
        "spain (remote)",
    )
)
# Alias de ciudades: el bucket es el nombre normalizado de la ciudad.
_CITY_ALIASES = {
    "malaga capital": "malaga",
    "provincia de malaga": "malaga",
    "barcelona city": "barcelona",
    "valencia city": "valencia",
    "sevilla": "sevilla",
    "seville": "sevilla",
    "la coruna": "a coruna",
    "coruna": "a coruna",
    "saragossa": "zaragoza",
}


def location_bucket(location: str) -> str:
    """'Málaga, Andalucía, España' -> 'malaga'; 'Remote' -> 'remote'; 'España' -> 'unknown'."""
    folded = fold(location)
    if not folded:
        return "unknown"
    if _REMOTE_WORDS.search(folded):
        return "remote"
    for part in (p.strip(" .") for p in re.split(r"[,;/|]| - ", folded)):
        if not part or part in _NON_CITY or part.isdigit():
            continue
        part = re.sub(r"^\d{5}\s+", "", part)  # código postal delante
        return _CITY_ALIASES.get(part, part)
    return "unknown"


# --- Modalidad -----------------------------------------------------------------------------

_MOD_REMOTE = re.compile(
    r"\b(?:100\s?% (?:remoto|remote|teletrabajo)|fully remote|full remote|remote[- ]first|100% remote|"
    r"teletrabajo (?:total|completo|100)|trabajo (?:en )?remoto|en remoto|remote position|remote role|"
    r"posicion remota|puesto remoto|work from anywhere|trabaja desde cualquier lugar|remote work)\b"
)
_MOD_HYBRID = re.compile(
    r"\b(?:hibrid[oa]|hybrid|modelo mixto|teletrabajo parcial|"
    r"\d (?:dias?|days?) (?:a la semana |per week |a week )?"
    r"(?:en (?:la )?oficina|in (?:the )?office|presencial(?:es)?|on-?site))\b"
)
_MOD_ONSITE = re.compile(
    r"\b(?:100\s?% presencial|presencial|on-?site|in-office|in office|en (?:nuestras )?oficinas|"
    r"trabajo en oficina|no remoto|not remote)\b"
)


def detect_modality(title: str, location: str, description: str, is_remote: bool | None) -> Modality:
    """Título y ubicación mandan (son explícitos); después la descripción; después la fuente."""
    head = fold(f"{title} {location}")
    if _MOD_HYBRID.search(head):
        return "hybrid"
    if _REMOTE_WORDS.search(head):
        return "remote"
    if _MOD_ONSITE.search(head):
        return "onsite"
    body = fold(description)
    hybrid, remote, onsite = (bool(p.search(body)) for p in (_MOD_HYBRID, _MOD_REMOTE, _MOD_ONSITE))
    if hybrid:
        return "hybrid"
    if remote and not onsite:
        return "remote"
    if onsite and not remote:
        return "onsite"
    if remote and onsite:
        return "hybrid"  # menciona las dos cosas: lo más habitual es un modelo mixto
    if is_remote is True:
        return "remote"
    return "unknown"


# --- URL canónica --------------------------------------------------------------------------

_TRACKING_PARAMS = re.compile(
    r"^(?:utm_.*|trk|trkinfo|trackingid|refid|ref|from|src|source|gclid|fbclid|mc_[a-z]+|"
    r"position|pagenum|currentjobid|origin|lipi|originalsubdomain|_ga|campaign|cmp|vjk|advn|tk|sjdu)$"
)
_LINKEDIN_ID = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*-)?(\d{6,})")
_INDEED_JK = re.compile(r"[?&](?:jk|vjk)=([0-9a-f]{8,})", re.I)


def canonical_url(url: str) -> str:
    match = _LINKEDIN_ID.search(url)
    if match:
        return f"https://www.linkedin.com/jobs/view/{match.group(1)}"
    if "indeed." in url.lower():
        jk = _INDEED_JK.search(url)
        if jk:
            return f"https://www.indeed.com/viewjob?jk={jk.group(1).lower()}"
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not _TRACKING_PARAMS.match(k.lower())
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            "https" if parts.scheme in ("http", "https") else parts.scheme,
            parts.netloc.lower().removeprefix("www."),
            path,
            urlencode(sorted(query)),
            "",
        )
    )


# --- Salario -------------------------------------------------------------------------------

_ANNUAL_FACTOR = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 220, "hourly": 1760}


def annual_salary_max(raw: RawJob) -> float | None:
    value = raw.salary_max or raw.salary_min
    if not value:
        return None
    return float(value) * _ANNUAL_FACTOR.get(raw.salary_interval or "yearly", 1)


# --- Idioma --------------------------------------------------------------------------------


# Palabras muy frecuentes de otros idiomas habituales en portales europeos (Arbeitnow, Remotive).
_OTHER_HINTS = frozenset(
    "der die das und wir sie mit fur ist nicht ein eine bei auf unser unsere ihre werden "
    "le les et nous vous pour avec est dans une des sur votre notre sont".split()
)
_ES_EN_HINTS = frozenset(
    "de la el los las y en con para que una por del somos buscamos "
    "the and of to in with for we you our are is will this".split()
)


def detect_offer_language(title: str, description: str) -> Language:
    text = f"{title}\n{description}"
    lang = detect_language(text)
    if lang in ("es", "en"):
        return lang
    words = re.findall(r"[a-z]+", fold(text))
    other = sum(w in _OTHER_HINTS for w in words)
    if other >= 8 and other > 2 * sum(w in _ES_EN_HINTS for w in words):
        return "other"
    return "unknown"


# --- Todo junto ----------------------------------------------------------------------------

# Fuentes cuyo `is_remote=False` es un dato real y no un valor por defecto.
_EXPLICIT_REMOTE_FLAG = frozenset({"arbeitnow"})


def normalize(raw: RawJob) -> NormalizedJob:
    description = clean_description(raw.description)
    title_norm = normalize_title(raw.title)
    company_norm = normalize_company(raw.company) or fold(raw.company)
    bucket = location_bucket(raw.location)
    modality = detect_modality(raw.title, raw.location, description, raw.is_remote)
    if bucket == "remote" and modality == "unknown":
        modality = "remote"
    elif modality == "unknown" and raw.is_remote is False and raw.site in _EXPLICIT_REMOTE_FLAG:
        modality = "onsite"  # el portal marca explícitamente que no es remoto (jobspy pone False por defecto)
    fingerprint_text = desc_fingerprint_text(description)
    return NormalizedJob(
        raw=raw,
        url_canonical=canonical_url(raw.url),
        title_norm=title_norm,
        company_norm=company_norm,
        location_bucket=bucket,
        modality=modality,
        language=detect_offer_language(raw.title, description),
        description=description,
        job_key=job_key(company_norm, title_norm, bucket),
        desc_sha256=sha256_hex(fingerprint_text),
        simhash=simhash_hex(fingerprint_text),
        salary_annual_max=annual_salary_max(raw),
    )
