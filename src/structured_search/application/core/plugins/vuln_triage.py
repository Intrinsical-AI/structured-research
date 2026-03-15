"""vuln_triage plugin declaration."""

from __future__ import annotations

from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.domain.vuln_triage.models import (
    VulnRecord,
    VulnTriageConstraints,
    VulnTriageTaskRuntimeConfig,
)

VULN_TRIAGE_PLUGIN = TaskPlugin(
    task_id="vuln_triage",
    name="Vulnerability Triage",
    prompt_namespace="vuln_triage",
    capabilities=frozenset({"jsonl_validate", "run"}),
    constraints_model=VulnTriageConstraints,
    record_model=VulnRecord,
    task_runtime_model=VulnTriageTaskRuntimeConfig,
    validate_task_runtime=True,
    include_user_profile_in_prompt=False,
    build_runtime=None,
)
