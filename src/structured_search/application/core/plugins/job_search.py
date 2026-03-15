"""job_search plugin declaration."""

from __future__ import annotations

from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.domain.job_search.models import JobPosting, JobSearchConstraints

JOB_SEARCH_PLUGIN = TaskPlugin(
    task_id="job_search",
    name="Job Search",
    prompt_namespace="job_search",
    capabilities=frozenset({"prompt", "jsonl_validate", "run"}),
    constraints_model=JobSearchConstraints,
    record_model=JobPosting,
    task_runtime_model=None,
    validate_task_runtime=False,
    include_user_profile_in_prompt=True,
    build_runtime=None,
)
