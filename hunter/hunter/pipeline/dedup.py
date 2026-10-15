"""Deduplicación en 3 capas (SPEC §6.3): identidad de origen, huella estable y SimHash del contenido."""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.services.text_utils import STOPWORDS, tokens

SIMHASH_BITS = 64
# Por debajo de estos tokens la descripción no identifica nada: no se calcula SimHash.
MIN_TOKENS_FOR_SIMHASH = 20
SHINGLE_SIZE = 3
NEAR_DUPLICATE_MAX_DISTANCE = 3  # capa 3: mismo contenido con retoques
SAME_KEY_MAX_DISTANCE = 12  # capa 2: misma empresa/título/zona y contenido parecido

# Líneas de pie de página que cambian entre portales y no describen el puesto.
_BOILERPLATE = re.compile(
    r"igualdad de oportunidades|equal opportunit|diversity|diversidad|discriminat|"
    r"proteccion de datos|data protection|privacy policy|politica de privacidad|"
    r"sobre nosotros|about us|quienes somos|who we are|follow us|siguenos",
)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def job_key(company_norm: str, title_norm: str, location_bucket: str) -> str:
    return sha256_hex(f"{company_norm}|{title_norm}|{location_bucket}")


def desc_fingerprint_text(description: str) -> str:
    """Tokens significativos de la descripción, sin boilerplate ni stopwords."""
    lines = [line for line in description.splitlines() if not _BOILERPLATE.search(line.lower())]
    words = [t for t in tokens("\n".join(lines)) if t not in STOPWORDS and len(t) > 1]
    return " ".join(words)


def _hash64(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(words: list[str]) -> int | None:
    if len(words) < MIN_TOKENS_FOR_SIMHASH:
        return None
    shingles = Counter(" ".join(words[i : i + SHINGLE_SIZE]) for i in range(len(words) - SHINGLE_SIZE + 1))
    vector = [0] * SIMHASH_BITS
    for shingle, weight in shingles.items():
        h = _hash64(shingle)
        for bit in range(SIMHASH_BITS):
            vector[bit] += weight if (h >> bit) & 1 else -weight
    return sum(1 << bit for bit in range(SIMHASH_BITS) if vector[bit] > 0)


def simhash_hex(fingerprint_text: str) -> str:
    """16 caracteres hex, o "" si la descripción es demasiado corta para compararla."""
    value = simhash(fingerprint_text.split())
    return "" if value is None else f"{value:016x}"


def hamming(a: str, b: str) -> int | None:
    """Distancia entre dos SimHash hex; None si alguno falta."""
    if not a or not b:
        return None
    return (int(a, 16) ^ int(b, 16)).bit_count()


# --- Decisión ------------------------------------------------------------------------------

DedupLayer = Literal["source", "job_key", "simhash", "fingerprint"]


# Nivel declarado en el título. Dos ofertas con el mismo texto pero distinto nivel (la empresa
# reutiliza la descripción para el puesto junior y el senior) son puestos distintos: si se fusionaran
# y llegara antes la senior (descartada), la junior se perdería.
_LEVELS = (
    (
        "intern",
        re.compile(r"\b(?:intern|internship|becari[oa]|practicas|trainee|werkstudent|stage|apprentice)\b"),
    ),
    ("junior", re.compile(r"\b(?:junior|jr|entry level|graduate)\b")),
    (
        "senior",
        re.compile(r"\b(?:senior|sr|lead|principal|staff|head|manager|director|architect|arquitecto)\b"),
    ),
)


def title_level(title_norm: str) -> str | None:
    for level, pattern in _LEVELS:
        if pattern.search(title_norm):
            return level
    return None


@dataclass(frozen=True)
class Candidate:
    job_id: str | None  # None: huella de una oferta ya purgada
    simhash: str
    level: str | None = None  # nivel del título (None: no declara nivel o huella purgada)


@dataclass(frozen=True)
class DedupDecision:
    duplicate: bool
    layer: DedupLayer | None = None
    job_id: str | None = None  # la oferta original (para alias o para actualizar last_seen)


NEW = DedupDecision(duplicate=False)


def decide_by_key(simhash_value: str, same_key: Iterable[Candidate]) -> DedupDecision:
    """Capa 2: misma empresa + título + zona. Es alias si el contenido es parecido (o no se puede
    comparar); si es muy distinto, es otro puesto con el mismo título."""
    for cand in same_key:
        distance = hamming(simhash_value, cand.simhash)
        if distance is None or distance <= SAME_KEY_MAX_DISTANCE:
            return DedupDecision(True, "job_key" if cand.job_id else "fingerprint", cand.job_id)
    return NEW


def decide_by_content(
    simhash_value: str, recent: Iterable[Candidate], level: str | None = None
) -> DedupDecision:
    """Capa 3: casi el mismo texto (retocado, o con otro título u otra empresa intermediaria),
    salvo que los títulos declaren niveles distintos (junior frente a senior)."""
    if not simhash_value:
        return NEW
    best: tuple[int, Candidate] | None = None
    for cand in recent:
        if level and cand.level and level != cand.level:
            continue
        distance = hamming(simhash_value, cand.simhash)
        if (
            distance is not None
            and distance <= NEAR_DUPLICATE_MAX_DISTANCE
            and (best is None or distance < best[0])
        ):
            best = (distance, cand)
    if best is None:
        return NEW
    return DedupDecision(True, "simhash" if best[1].job_id else "fingerprint", best[1].job_id)
