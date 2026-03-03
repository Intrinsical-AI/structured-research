"""Compatibility tests for shared BaseJobEntry extraction."""

from structured_search.domain.common.models import BaseJobEntry as SharedBaseJobEntry
from structured_search.domain.gen_cv.models import JobDescription
from structured_search.domain.job_search.models import (
    BaseJobEntry as JobSearchBaseJobEntry,
)


def test_job_search_reexports_shared_base_job_entry():
    assert JobSearchBaseJobEntry is SharedBaseJobEntry


def test_gen_cv_job_description_inherits_shared_base_job_entry():
    assert issubclass(JobDescription, SharedBaseJobEntry)
