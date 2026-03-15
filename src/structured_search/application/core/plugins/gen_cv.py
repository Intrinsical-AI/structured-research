"""gen_cv plugin declaration."""

from __future__ import annotations

from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.domain.models import BaseConstraints

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
    action_handlers={},
)
