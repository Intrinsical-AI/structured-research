"""Job-search ETL service kept under application plugin support modules."""

from __future__ import annotations

from structured_search.domain.job_search.models import (
    JobPosting,
    JobSearchConstraints,
    ScoredJobPosting,
)
from structured_search.domain.scoring import ScoredResult
from structured_search.ports.etl import BaseETLService


class ETLJobSearch(BaseETLService[JobSearchConstraints, JobPosting, ScoredJobPosting]):
    """Load → Process → Export pipeline for job postings."""

    def _parse(self, raw: dict) -> JobPosting:
        return JobPosting.model_validate(raw)

    def _to_scored(self, scored: ScoredResult) -> ScoredJobPosting:
        return ScoredJobPosting.model_validate(scored.model_dump())
