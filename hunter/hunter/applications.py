"""Candidaturas (SPEC §18.4): resumen, aviso de "¿sin respuesta?" y exportación para Excel.

Lógica pura sobre `ApplicationRecord`: la API la usa y los tests la prueban sin base de datos.
"""

import codecs
import csv
import io
from collections.abc import Iterable
from datetime import datetime, timedelta

from app.services.text_utils import fold

from hunter.api.schemas import ApplicationDetail, ApplicationItem, ApplicationStats, ScoreBand
from hunter.models import ApplicationRecord, ApplicationStatus

STALE_AFTER = timedelta(days=21)
# La empresa ha contestado, para bien o para mal.
RESPONDED: frozenset[str] = frozenset({"in_process", "interview", "offer", "rejected"})
STATUS_LABEL: dict[ApplicationStatus, str] = {
    "applied": "Enviada",
    "in_process": "En proceso",
    "interview": "Entrevista",
    "offer": "Oferta",
    "rejected": "Rechazada",
    "no_response": "Sin respuesta",
    "withdrawn": "Retirada",
}
# Tramos de compatibilidad del CV enviado: [mínimo, máximo).
BANDS = (("80 % o más", 80, 101), ("Entre 60 y 79 %", 60, 80), ("Menos de 60 %", 0, 60))
WITHOUT_SCORE = "Sin pasar por el Optimizador"


def reached(app: ApplicationRecord, statuses: Iterable[str]) -> bool:
    """Si la candidatura está o estuvo en alguno de esos estados (una entrevista que acabó en
    rechazo cuenta como entrevista)."""
    wanted = set(statuses)
    return app.status in wanted or any(e.status in wanted for e in app.events)


def is_stale(app: ApplicationRecord, now: datetime) -> bool:
    return app.status == "applied" and now - app.status_changed_at >= STALE_AFTER


def compute_stats(apps: list[ApplicationRecord], now: datetime) -> ApplicationStats:
    scores = [a.ats_score_after for a in apps if a.ats_score_after is not None]

    def band(label: str, members: list[ApplicationRecord]) -> ScoreBand:
        responded = sum(reached(a, RESPONDED) for a in members)
        return ScoreBand(label=label, total=len(members), responded=responded)

    bands = [
        band(label, [a for a in apps if a.ats_score_after is not None and low <= a.ats_score_after < high])
        for label, low, high in BANDS
    ]
    without = [a for a in apps if a.ats_score_after is None]
    if without:
        bands.append(band(WITHOUT_SCORE, without))
    week_ago = now - timedelta(days=7)
    return ApplicationStats(
        total=len(apps),
        last_7_days=sum(a.applied_at >= week_ago for a in apps),
        awaiting=sum(a.status == "applied" for a in apps),
        responded=sum(reached(a, RESPONDED) for a in apps),
        interviews=sum(reached(a, ("interview", "offer")) for a in apps),
        offers=sum(reached(a, ("offer",)) for a in apps),
        stale=sum(is_stale(a, now) for a in apps),
        avg_ats_after=round(sum(scores) / len(scores)) if scores else None,
        by_band=bands,
    )


def select(
    apps: list[ApplicationRecord], status: ApplicationStatus | None = None, q: str | None = None
) -> list[ApplicationRecord]:
    needle = fold(q).strip() if q else ""
    return [
        a
        for a in apps
        if (status is None or a.status == status)
        and (not needle or needle in fold(f"{a.company} {a.title} {a.location} {a.notes}"))
    ]


def to_item(app: ApplicationRecord, now: datetime) -> ApplicationItem:
    data = app.model_dump(exclude={"offer_text", "cv_markdown"})
    return ApplicationItem(**data, stale=is_stale(app, now))


def to_detail(app: ApplicationRecord, now: datetime) -> ApplicationDetail:
    return ApplicationDetail(
        **to_item(app, now).model_dump(), offer_text=app.offer_text, cv_markdown=app.cv_markdown
    )


CSV_HEADER = (
    "Fecha",
    "Empresa",
    "Puesto",
    "Ubicación",
    "Estado",
    "Compatibilidad del CV enviado (%)",
    "Compatibilidad del CV original (%)",
    "Nota del Buscador",
    "Enlace",
    "Notas",
    "Último cambio",
)


def _cell(value: object) -> str:
    """Texto seguro para una hoja de cálculo: las ofertas vienen de internet, y una celda que empieza
    por = + - @ la interpretaría Excel como fórmula (inyección CSV)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(apps: list[ApplicationRecord]) -> bytes:
    """CSV para Excel en español: separador `;`, fechas dd/mm/aaaa y BOM UTF-8 (para las tildes)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for a in apps:
        writer.writerow(
            _cell(v)
            for v in (
                f"{a.applied_at.astimezone():%d/%m/%Y}",
                a.company,
                a.title,
                a.location,
                STATUS_LABEL[a.status],
                a.ats_score_after,
                a.ats_score_before,
                a.judge_score,
                a.url,
                a.notes,
                f"{a.status_changed_at.astimezone():%d/%m/%Y}",
            )
        )
    return codecs.BOM_UTF8 + buffer.getvalue().encode("utf-8")
