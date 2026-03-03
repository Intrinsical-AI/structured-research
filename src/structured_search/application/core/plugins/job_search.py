"""job_search plugin declaration."""

from __future__ import annotations

from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.domain.job_search.models import JobPosting, JobSearchConstraints
from structured_search.infra.config_loader import TaskRuntimeConfig, task_json_to_scoring_config
from structured_search.infra.scoring import HeuristicScorer


def _build_runtime(constraints_payload: dict, task_payload: dict):
    constraints = JobSearchConstraints.model_validate(constraints_payload)
    scoring_config = task_json_to_scoring_config(task_payload)
    scorer = HeuristicScorer(config=scoring_config)
    return constraints, scorer


JOB_SEARCH_PLUGIN = TaskPlugin(
    task_id="job_search",
    name="Job Search",
    prompt_namespace="job_search",
    capabilities=frozenset({"prompt", "jsonl_validate", "run"}),
    constraints_model=JobSearchConstraints,
    record_model=JobPosting,
    task_runtime_model=TaskRuntimeConfig,
    validate_task_runtime=True,
    include_user_profile_in_prompt=True,
    build_runtime=_build_runtime,
)
