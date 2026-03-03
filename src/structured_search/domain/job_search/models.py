"""Job-search task domain models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from structured_search.domain import BaseConstraints, BaseResult, BaseUserProfile, ScoredResult
from structured_search.domain.common import BaseJobEntry


class JobSearchConstraints(BaseConstraints):
    domain: Literal["job_search"] = "job_search"


class CommutePolicyConfig(BaseModel):
    hybrid_madrid_toledo_max_days_per_week: int | None = None
    max_hybrid_days_per_week: int | None = None


class ProcessPreferences(BaseModel):
    prefer_startup: bool = False
    prefer_enterprise: bool = False
    prefer_take_home: bool = False
    avoid_whiteboard_only: bool = False


class JobSearchUserProfile(BaseUserProfile):
    role_focus: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    process_preferences: ProcessPreferences = Field(default_factory=ProcessPreferences)
    commute_policy: CommutePolicyConfig = Field(default_factory=CommutePolicyConfig)
    work_authorization_required_for_user: bool = False
    availability_days: int = 7


class GeoInfo(BaseModel):
    region: str
    city: str | None = None
    country: str | None = None


class SeniorityInfo(BaseModel):
    level: Literal["junior", "mid", "senior", "staff"]


class RecencyInfo(BaseModel):
    activity_age_days: int | None = None


class EconomicsInfo(BaseModel):
    salary_eur_gross: float | None = None
    salary_usd_gross: float | None = None
    period: str | None = None


class DomainInfo(BaseModel):
    tags: list[str] = Field(default_factory=list)


class MobilityInfo(BaseModel):
    supported_regions: list[str] = Field(default_factory=list)


class JobPosting(BaseResult, BaseJobEntry):
    model_config = ConfigDict(extra="allow")

    modality: Literal["remote", "hybrid", "on_site"]  # type: ignore[assignment]
    seniority: SeniorityInfo  # type: ignore[assignment]

    posted_at: date | datetime | None = None
    apply_url: AnyUrl
    geo: GeoInfo

    title_canonical: str | None = None
    onsite_days_per_week: float | None = None
    mobility: MobilityInfo | None = None
    visa_sponsorship_offered: bool | None = None
    recency: RecencyInfo | None = None
    economics: EconomicsInfo | None = None
    domain: DomainInfo | None = None
    process: list[str] | None = None
    on_site_only: bool | None = None
    k8s_primary: bool | None = None


class ScoredJobPosting(JobPosting, ScoredResult):
    pass
