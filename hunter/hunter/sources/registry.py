"""Construye la lista de fuentes activas a partir de las Reglas de Oro."""

import httpx

from hunter.rules.schema import GoldenRules
from hunter.sources.base import JobSource
from hunter.sources.feeds import ArbeitnowSource, RemotiveSource, RssSource
from hunter.sources.jobspy_source import JobspySource

_JOBSPY_ORDER = ("linkedin", "indeed", "google")


def build_sources(
    rules: GoldenRules, client: httpx.AsyncClient, pause_s: tuple[float, float]
) -> list[JobSource]:
    used_sites = {site for q in rules.search.queries for site in q.sites}
    sources: list[JobSource] = [
        JobspySource(site, pause_s=pause_s) for site in _JOBSPY_ORDER if site in used_sites
    ]
    if "remotive" in rules.search.feeds:
        sources.append(RemotiveSource(client))
    if "arbeitnow" in rules.search.feeds:
        sources.append(ArbeitnowSource(client))
    sources.extend(RssSource(client, feed) for feed in rules.search.rss)
    return sources
