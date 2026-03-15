"""In-process registry for task plugins."""

from __future__ import annotations

from dataclasses import dataclass

from structured_search.application.core.plugins.gen_cv import GEN_CV_PLUGIN
from structured_search.application.core.plugins.job_search import JOB_SEARCH_PLUGIN
from structured_search.application.core.plugins.product_search import PRODUCT_SEARCH_PLUGIN
from structured_search.application.core.plugins.vuln_triage import VULN_TRIAGE_PLUGIN
from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.contracts import TaskSummary


@dataclass(frozen=True)
class TaskRegistry:
    plugins: dict[str, TaskPlugin]

    def list(self) -> list[TaskSummary]:
        return [
            TaskSummary(task_id=p.task_id, name=p.name, capabilities=sorted(p.capabilities))
            for _, p in sorted(self.plugins.items(), key=lambda item: item[0])
        ]

    def get(self, task_id: str) -> TaskPlugin:
        try:
            return self.plugins[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task_id: {task_id!r}") from exc


_DEFAULT_REGISTRY = TaskRegistry(
    plugins={
        JOB_SEARCH_PLUGIN.task_id: JOB_SEARCH_PLUGIN,
        GEN_CV_PLUGIN.task_id: GEN_CV_PLUGIN,
        PRODUCT_SEARCH_PLUGIN.task_id: PRODUCT_SEARCH_PLUGIN,
        VULN_TRIAGE_PLUGIN.task_id: VULN_TRIAGE_PLUGIN,
    }
)


def get_task_registry() -> TaskRegistry:
    return _DEFAULT_REGISTRY
