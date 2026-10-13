"""Normalización de texto compartida por el validador y el detector de cambios."""

import re
import unicodedata

# Equivalencias veraces permitidas (SDD regla 5). Bidireccionales.
_SYNONYM_GROUPS = [
    {"javascript", "js"},
    {"typescript", "ts"},
    {"kubernetes", "k8s"},
    {"postgresql", "postgres"},
    {"python", "py"},
    {"amazon web services", "aws"},
    {"google cloud platform", "gcp", "google cloud"},
    {"machine learning", "ml", "aprendizaje automatico"},
    {"inteligencia artificial", "ia", "ai", "artificial intelligence"},
    {"ci/cd", "integracion continua", "continuous integration"},
    {"node.js", "nodejs", "node"},
    {"react", "react.js", "reactjs"},
    {"vue", "vue.js", "vuejs"},
    {"ingles", "english"},
    {"espanol", "castellano", "spanish"},
    {"sql server", "mssql"},
]
SYNONYMS: dict[str, set[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _term in _group:
        SYNONYMS.setdefault(_term, set()).update(_group - {_term})

STOPWORDS = frozenset(
    "de del la las el los y e o u en con para por a al un una sus su lo que como "
    "the and or of in at for with to a an on by as from".split()
)

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_NOISE = re.compile(r"[*_`#>]+")


def fold(text: str) -> str:
    """Minúsculas, sin tildes y con espacios normalizados (para comparar textos)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", fold(text))


def stem(token: str) -> str:
    # Plural muy simple (apis -> api, servicios -> servicio, bases -> base).
    if len(token) > 4 and token.endswith("es") and not token.endswith("ies"):
        return token[:-1] if token[-3] in "aeiou" else token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def clean_markdown(text: str) -> str:
    """Quita imágenes, enlaces (conserva su texto) y marcas de formato de Markdown."""
    text = _MD_LINK.sub(r"\1", _MD_IMAGE.sub(" ", text))
    return _MD_NOISE.sub("", text).strip()
