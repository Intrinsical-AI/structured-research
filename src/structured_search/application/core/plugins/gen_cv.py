"""gen_cv plugin declaration."""

from __future__ import annotations

from structured_search.application.common.dependencies import ApplicationDependencies
from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.application.gen_cv.generate_cv import gen_cv
from structured_search.contracts import CandidateInput, GenCVResponse
from structured_search.domain.models import BaseConstraints


def _run_gen_cv_action(
    *,
    profile_id: str,
    job: dict,
    candidate_profile: CandidateInput | dict,
    selected_claim_ids: list[str] | None = None,
    llm_model: str | None = None,
    allow_mock_fallback: bool = True,
    deps: ApplicationDependencies | None = None,
) -> GenCVResponse:
    return gen_cv(
        task_id="gen_cv",
        profile_id=profile_id,
        job=job,
        candidate_profile=candidate_profile,
        selected_claim_ids=selected_claim_ids,
        llm_model=llm_model,
        allow_mock_fallback=allow_mock_fallback,
        deps=deps,
    )


GEN_CV_PLUGIN = TaskPlugin(
    task_id="gen_cv",
    name="GEN CV",
    prompt_namespace="gen_cv",
    capabilities=frozenset({"action:gen-cv"}),
    constraints_model=BaseConstraints,
    record_model=None,
    task_runtime_model=None,
    validate_task_runtime=False,
    include_user_profile_in_prompt=False,
    build_runtime=None,
    action_handlers={"gen-cv": _run_gen_cv_action},
)
