"""CV generation domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from structured_search.domain import BaseResult
from structured_search.tasks.common.models import BaseJobEntry


class JobDescription(BaseJobEntry):
    """Flexible job description — input for CV generation.

    Extends BaseJobEntry with an explicit id and an extra dict for
    unstructured fields. All common job fields (title, company, stack,
    seniority, modality, location, description, url) are inherited.
    """

    id: str
    extra: dict[str, Any] = Field(default_factory=dict)


class ExperienceEntry(BaseModel):
    company: str
    title: str
    duration_months: int | None = None
    highlights: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)


class SkillSet(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class CandidateAtomsProfile(BaseModel):
    """Candidate profile as grounded atoms summary — input for CV generation."""

    id: str
    name: str | None = None
    seniority: str
    tech_stack: SkillSet = Field(default_factory=SkillSet)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    spoken_languages: list[str] = Field(default_factory=list)
    location: str | None = None
    timezone: str | None = None
    availability_days: int = 30


class CVOutput(BaseModel):
    """Validated LLM output — intermediate before GeneratedCV."""

    summary: str
    highlights: list[str] = Field(default_factory=list, max_length=5)
    cited_claim_ids: list[str] = Field(default_factory=list)


class GeneratedCV(BaseResult):
    """Output of CV generation.

    Extends BaseResult to inherit evidence anchoring, provenance tracking
    (extracted_at), anomaly detection, and facts/inferences structure.

    Required fields from BaseResult: id, source.
    The id is typically '{job_id}__{candidate_id}'.
    The source is typically the LLM class name or 'gen_cv'.
    extracted_at (from BaseResult) serves as the generation timestamp.
    """

    job_id: str
    candidate_id: str
    title: str | None = None
    summary: str
    highlights: list[str] = Field(default_factory=list)
    grounded_claim_ids: list[str] = Field(default_factory=list)
    model_used: str | None = None
    raw_output: str | None = None
