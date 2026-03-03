"""Job search ETL service."""

from __future__ import annotations

from structured_search.domain.scoring import ScoredResult
from structured_search.ports.etl import BaseETLService
from structured_search.tasks.job_search.models import (
    JobPosting,
    JobSearchConstraints,
    ScoredJobPosting,
)


class ETLJobSearch(BaseETLService[JobSearchConstraints, JobPosting, ScoredJobPosting]):
    """Load → Process → Export pipeline for job postings."""

    def _parse(self, raw: dict) -> JobPosting:
        return JobPosting.model_validate(raw)

    def _to_scored(self, scored: ScoredResult) -> ScoredJobPosting:
        return ScoredJobPosting.model_validate(scored.model_dump())
