"""Feeds públicos de empleo tech: Remotive (JSON), Arbeitnow (JSON) y RSS/Atom genéricos.

Uso personal y de bajo volumen: una o dos peticiones por ejecución, respetando sus condiciones
(Remotive pide enlazar a la oferta original, cosa que la vista hace siempre).
"""

import xml.etree.ElementTree as ET  # noqa: S405 — feeds configurados por el usuario; expat limita expansiones
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from hunter.rules.schema import GoldenRules, RssFeed
from hunter.sources.base import FetchResult, JobSource, SourceBlockedError, SourceError, validate_rows

USER_AGENT = "cv-optimizer-hunter/0.1 (uso personal; +https://github.com/francisykza/cv-optimizer)"
MAX_FEED_BYTES = 10 * 1024 * 1024


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    try:
        response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
    except httpx.TimeoutException as exc:
        raise SourceError(f"Timeout al leer {url}", code="TIMEOUT") from exc
    except httpx.TransportError as exc:
        raise SourceError(f"No se pudo conectar: {type(exc).__name__}", code="NETWORK") from exc
    if response.status_code in (403, 429):
        raise SourceBlockedError(f"HTTP {response.status_code} en {url}", code=f"HTTP_{response.status_code}")
    if response.status_code != 200:
        raise SourceError(f"HTTP {response.status_code} en {url}", code=f"HTTP_{response.status_code}")
    if len(response.content) > MAX_FEED_BYTES:
        raise SourceError("Respuesta demasiado grande", code="TOO_LARGE")
    return response


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError("La respuesta no es JSON válido", code="BAD_JSON") from exc


def _date_from_iso(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


class RemotiveSource(JobSource):
    name = "remotive"
    url = "https://remotive.com/api/remote-jobs"

    def __init__(self, client: httpx.AsyncClient, category: str = "software-dev", limit: int = 100) -> None:
        self._client = client
        self._params = {"category": category, "limit": limit}

    async def fetch(self, rules: GoldenRules) -> FetchResult:
        data = _json(await _get(self._client, self.url, self._params))
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            raise SourceError("Formato inesperado de Remotive", code="BAD_FORMAT")
        return validate_rows((self._row(j) for j in jobs if isinstance(j, dict)), self.name)

    @staticmethod
    def _row(job: dict[str, Any]) -> dict[str, Any]:
        scope = (job.get("candidate_required_location") or "").strip()
        return {
            "site": "remotive",
            "site_job_id": str(job.get("id") or "") or None,
            "url": job.get("url") or "",
            "title": job.get("title") or "",
            "company": job.get("company_name") or "",
            # El ámbito ("USA Only", "Europe") va en la ubicación: la regla LOC_REMOTE_SCOPE lo lee.
            "location": f"Remote ({scope})" if scope else "Remote",
            "is_remote": True,
            "date_posted": _date_from_iso(job.get("publication_date")),
            "description": job.get("description") or "",
        }


class ArbeitnowSource(JobSource):
    name = "arbeitnow"
    url = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, client: httpx.AsyncClient, pages: int = 2) -> None:
        self._client = client
        self._pages = pages

    async def fetch(self, rules: GoldenRules) -> FetchResult:
        rows: list[dict[str, Any]] = []
        for page in range(1, self._pages + 1):
            data = _json(await _get(self._client, self.url, {"page": page}))
            items = data.get("data") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise SourceError("Formato inesperado de Arbeitnow", code="BAD_FORMAT")
            rows.extend(self._row(j) for j in items if isinstance(j, dict))
            if not (data.get("links") or {}).get("next"):
                break
        return validate_rows(rows, self.name)

    @staticmethod
    def _row(job: dict[str, Any]) -> dict[str, Any]:
        created = job.get("created_at")
        posted = datetime.fromtimestamp(created, UTC).date() if isinstance(created, int | float) else None
        return {
            "site": "arbeitnow",
            "site_job_id": job.get("slug") or None,
            "url": job.get("url") or "",
            "title": job.get("title") or "",
            "company": job.get("company_name") or "",
            "location": job.get("location") or "",
            "is_remote": bool(job.get("remote")) if job.get("remote") is not None else None,
            "date_posted": posted,
            "description": job.get("description") or "",
        }


_ATOM = "{http://www.w3.org/2005/Atom}"


class RssSource(JobSource):
    """RSS 2.0 o Atom. La empresa se deduce de "Puesto at/en Empresa" o se usa el nombre del feed."""

    def __init__(self, client: httpx.AsyncClient, feed: RssFeed) -> None:
        self._client = client
        self._feed = feed
        self.name = f"rss:{feed.name}"

    async def fetch(self, rules: GoldenRules) -> FetchResult:
        response = await _get(self._client, self._feed.url)
        try:
            root = ET.fromstring(response.content)  # noqa: S314
        except ET.ParseError as exc:
            raise SourceError("El feed no es XML válido", code="BAD_XML") from exc
        items = root.iter("item") if root.find(".//item") is not None else root.iter(f"{_ATOM}entry")
        return validate_rows((self._row(item) for item in items), self.name)

    def _row(self, item: ET.Element) -> dict[str, Any]:
        def text(*tags: str) -> str:
            for tag in tags:
                node = item.find(tag)
                if node is not None and (node.text or "").strip():
                    return node.text.strip()
            return ""

        link = text("link")
        atom_link = item.find(f"{_ATOM}link")
        if not link and atom_link is not None:
            link = atom_link.get("href", "")
        title = text("title", f"{_ATOM}title")
        company = self._feed.name
        for sep in (" at ", " en ", " @ "):
            if sep in title:
                title, company = title.rsplit(sep, 1)
                break
        return {
            "site": "rss",
            "site_job_id": text("guid", f"{_ATOM}id") or None,
            "url": link,
            "title": title,
            "company": company,
            "location": text("location", "region"),
            "date_posted": _rss_date(text("pubDate", f"{_ATOM}updated", f"{_ATOM}published")),
            "description": text(
                "description",
                "{http://purl.org/rss/1.0/modules/content/}encoded",
                f"{_ATOM}content",
                f"{_ATOM}summary",
            ),
        }


def _rss_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        return _date_from_iso(value)
