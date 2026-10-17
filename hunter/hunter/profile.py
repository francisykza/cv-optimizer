"""Tu perfil (SPEC §19): leerlo, guardarlo desde la web y saber qué notas se han quedado viejas.

- Sigue siendo un Markdown en la carpeta de datos (`profile.md`), que también se puede editar a mano. La web
  lo guarda con escritura atómica (temporal + fsync + `os.replace`) y deja la versión anterior al lado
  (`profile.anterior.md`).
- Solo se lee o se escribe un `.md` dentro de la carpeta de datos: `judge.profile_file` admite rutas
  absolutas y, con la API, una ruta cualquiera permitiría leer o escribir cualquier archivo del equipo
  (por ejemplo `hunter/.env`).
- Como mucho `PROFILE_MAX_CHARS` caracteres: es lo que lee el juez.
- Su contenido nunca va a los logs.
"""

import hashlib
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.text_utils import fold

from hunter import services
from hunter.config import HUNTER_ROOT, Settings
from hunter.judge.judge import PROFILE_MAX_CHARS
from hunter.judge.limiter import BudgetGuard
from hunter.pipeline.prescore import profile_terms
from hunter.pipeline.run import REJUDGE_DAYS, outdated_jobs
from hunter.rules.schema import GoldenRules
from hunter.store.repository import Repository, utcnow

EXAMPLE = HUNTER_ROOT / "profile.example.md"
MAX_CHARS = PROFILE_MAX_CHARS
# Media de tokens por oferta mientras no haya veredictos propios con los que calcularla (run real: ~3.300).
DEFAULT_TOKENS_PER_JOB = 3300
# Lo que tarda Groq en contestar cada oferta, aparte de la espera del limitador por minuto.
LATENCY_PER_JOB_S = 15
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ProfilePathError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} no es un .md de la carpeta de datos")
        self.path = path


class ProfileConflictError(Exception):
    """El archivo cambió (a mano, fuera de la web) desde que se leyó."""


class ProfileTextError(ValueError):
    """Perfil vacío o más largo de lo que lee el juez."""


@dataclass(frozen=True)
class ProfileFile:
    text: str
    sha256: str
    exists: bool
    updated_at: datetime | None


@dataclass(frozen=True)
class Outdated:
    """Notas de la última semana que son de un perfil anterior y lo que costaría ponerlas al día."""

    count: int
    from_cache: int  # ya se juzgaron con este perfil: se recuperan sin gastar tokens
    days: int
    est_tokens: int
    est_minutes: int
    tokens_left_today: int | None  # None: sin tope diario (HUNTER_DAILY_TOKEN_BUDGET=0)


def thousands(n: int) -> str:
    """Como la web (es-ES): 4000 sin separador, 69.000 con punto."""
    return str(n) if n < 10_000 else f"{n:,}".replace(",", ".")


def resolve(rules: GoldenRules, settings: Settings) -> Path:
    """Ruta del perfil, siempre un `.md` dentro de la carpeta de datos; si no, ProfilePathError."""
    path = services.profile_path(rules, settings).resolve()
    if path.suffix.lower() != ".md" or not path.is_relative_to(settings.data_dir.resolve()):
        raise ProfilePathError(path)
    return path


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.anterior.md")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean(text: str) -> str:
    """Saltos de línea de Unix, sin caracteres de control ni espacios al final de las líneas, sin líneas
    vacías al principio ni al final y con un salto de línea final."""
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    body = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    return body + "\n" if body.strip() else ""


def size(text: str) -> int:
    """Caracteres que cuentan para el límite: los que recibe el juez."""
    return len(text.strip())


def read(path: Path) -> ProfileFile:
    try:
        text = path.read_text(encoding="utf-8")
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except FileNotFoundError:
        return ProfileFile("", digest(""), False, None)
    return ProfileFile(text, digest(text), True, updated_at)


def read_previous(path: Path) -> str | None:
    try:
        return backup_path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def is_example(text: str) -> bool:
    """¿Es todavía el perfil de ejemplo que copia `python -m hunter init`?"""
    try:
        example = EXAMPLE.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.sub(r"\s+", " ", text).strip() == re.sub(r"\s+", " ", example).strip()


def terms(text: str) -> list[str]:
    """Lo que buscará el pre-score en las ofertas, sin repetidos."""
    seen: set[str] = set()
    out: list[str] = []
    for term in profile_terms(text):
        key = fold(term)
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out


def save(path: Path, text: str, base_sha256: str) -> ProfileFile:
    """Valida y guarda. `base_sha256` es el del archivo que se editó: si ya no coincide, alguien lo ha
    cambiado fuera de la web y no se pisa (ProfileConflictError)."""
    content = clean(text)
    chars = size(content)
    if chars == 0:
        raise ProfileTextError("El perfil está vacío: el juez no tendría con qué comparar las ofertas.")
    if chars > MAX_CHARS:
        raise ProfileTextError(
            f"El perfil tiene {thousands(chars)} caracteres y el juez lee como mucho {thousands(MAX_CHARS)}: "
            "acórtalo."
        )
    current = read(path)
    if current.sha256 != base_sha256:
        raise ProfileConflictError()
    if current.exists and current.text == content:
        return current
    path.parent.mkdir(parents=True, exist_ok=True)
    if current.exists and current.text.strip():
        _write_atomic(backup_path(path), current.text)
    _write_atomic(path, content)
    return read(path)


def _write_atomic(path: Path, text: str) -> None:
    """Nunca queda un archivo a medias: se escribe en un temporal de la misma carpeta y se sustituye."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:  # Windows: otro proceso lo está leyendo en este instante
                if attempt == 4:
                    raise
                time.sleep(0.05)
    finally:
        tmp.unlink(missing_ok=True)


def outdated(repo: Repository, rules: GoldenRules, settings: Settings, profile_text: str) -> Outdated:
    """Cuántas notas de la última semana son de un perfil anterior y cuánto costaría volver a juzgarlas
    (las que ya tienen nota con este perfil en la caché salen gratis)."""
    key_of = services.current_verdict_key(rules, settings, profile_text)
    jobs = outdated_jobs(repo, utcnow() - timedelta(days=REJUDGE_DAYS), key_of)
    from_cache = sum(
        1
        for job in jobs
        if (stored := repo.cached_verdict(key_of(job))) is not None and stored.status == "ok"
    )
    to_judge = len(jobs) - from_cache
    per_job = repo.avg_verdict_tokens() or DEFAULT_TOKENS_PER_JOB
    per_minute = max(1, settings.hunter_tokens_per_minute)
    seconds = to_judge * (per_job / per_minute * 60 + LATENCY_PER_JOB_S)
    budget = settings.hunter_daily_token_budget
    return Outdated(
        count=len(jobs),
        from_cache=from_cache,
        days=REJUDGE_DAYS,
        est_tokens=to_judge * per_job,
        est_minutes=math.ceil(seconds / 60),
        tokens_left_today=BudgetGuard(repo, budget).remaining() if budget > 0 else None,
    )
