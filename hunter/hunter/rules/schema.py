"""Reglas de Oro (SPEC §5): esquema validado y versión estable."""

import hashlib
import json
from typing import Literal

from app.services.text_utils import fold
from pydantic import BaseModel, ConfigDict, Field, field_validator

JobspySite = Literal["linkedin", "indeed", "google"]
FeedName = Literal["remotive", "arbeitnow"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _clean_terms(values: list[str]) -> list[str]:
    """Normaliza listas de términos: sin vacíos ni duplicados (comparando sin tildes)."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = value.strip()
        key = fold(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


class SearchQuery(_Strict):
    term: str = Field(min_length=2, max_length=200)
    google_term: str | None = Field(default=None, max_length=300)
    location: str = Field(default="España", max_length=200)
    sites: list[JobspySite] = Field(default_factory=lambda: ["linkedin", "indeed"])
    hours_old: int = Field(default=48, ge=1, le=24 * 30)
    results_wanted: int = Field(default=30, ge=1, le=100)
    is_remote: bool | None = None


class RssFeed(_Strict):
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=8, max_length=2048)


class SearchConfig(_Strict):
    queries: list[SearchQuery] = Field(default_factory=list, max_length=20)
    country_indeed: str = "spain"
    feeds: list[FeedName] = Field(default_factory=list)
    rss: list[RssFeed] = Field(default_factory=list, max_length=20)


class LocationRules(_Strict):
    home_area: str = "malaga"
    onsite_allowed_areas: list[str] = Field(default_factory=list)
    accept_remote: bool = True
    remote_scopes: list[str] = Field(default_factory=lambda: ["spain", "europe", "emea", "worldwide"])
    accept_hybrid_outside_area: bool = False
    # Países donde aceptas puestos no remotos. Fuera de ellos, solo pasa lo que diga que es remoto.
    home_countries: list[str] = Field(default_factory=lambda: ["spain"])

    @field_validator("onsite_allowed_areas", "remote_scopes", "home_countries")
    @classmethod
    def _fold_areas(cls, value: list[str]) -> list[str]:
        return [fold(x) for x in _clean_terms(value)]


class ExperienceRules(_Strict):
    max_years_required: int | None = Field(default=None, ge=0, le=30)
    unknown_years: Literal["pass"] = "pass"


class SeniorityRules(_Strict):
    exclude_title_terms: list[str] = Field(default_factory=list)

    @field_validator("exclude_title_terms")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        return _clean_terms(value)


class Blacklists(_Strict):
    companies: list[str] = Field(default_factory=list)
    intermediary_signals: list[str] = Field(default_factory=list)
    title_terms: list[str] = Field(default_factory=list)
    description_terms: list[str] = Field(default_factory=list)

    @field_validator("companies", "intermediary_signals", "title_terms", "description_terms")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        return _clean_terms(value)


class RequiredAny(_Strict):
    terms: list[str] = Field(default_factory=list)
    min_hits: int = Field(default=1, ge=0, le=20)

    @field_validator("terms")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        return _clean_terms(value)


class LanguageRules(_Strict):
    allowed: list[Literal["es", "en", "other"]] = Field(default_factory=lambda: ["es", "en"])


class SalaryRules(_Strict):
    min_annual_eur: float | None = Field(default=None, ge=0)


class FreshnessRules(_Strict):
    max_age_days: int | None = Field(default=21, ge=1, le=365)


class JudgeRules(_Strict):
    """Lo usa el juez IA (Fase 2). No afecta a la guillotina."""

    profile_file: str = "data/profile.md"
    priorities: list[str] = Field(default_factory=list, max_length=10)
    soft_dislikes: list[str] = Field(default_factory=list, max_length=10)
    min_score_to_show: int = Field(default=55, ge=0, le=100)


class GoldenRules(_Strict):
    schema_version: Literal[1] = 1
    search: SearchConfig = Field(default_factory=SearchConfig)
    location: LocationRules = Field(default_factory=LocationRules)
    experience: ExperienceRules = Field(default_factory=ExperienceRules)
    seniority: SeniorityRules = Field(default_factory=SeniorityRules)
    blacklists: Blacklists = Field(default_factory=Blacklists)
    required_any: RequiredAny = Field(default_factory=RequiredAny)
    languages: LanguageRules = Field(default_factory=LanguageRules)
    salary: SalaryRules = Field(default_factory=SalaryRules)
    freshness: FreshnessRules = Field(default_factory=FreshnessRules)
    judge: JudgeRules = Field(default_factory=JudgeRules)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    @property
    def version(self) -> str:
        """sha256[:12] del JSON canónico: el mismo contenido da siempre la misma versión."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:12]
