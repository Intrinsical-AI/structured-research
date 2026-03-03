"""Task plugin contract for structured-search core services."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from structured_search.domain import BaseConstraints
from structured_search.ports.scoring import ScoringPort

BuildRuntimeFn = Callable[[dict[str, Any], dict[str, Any]], tuple[BaseConstraints, ScoringPort]]
ActionHandlerFn = Callable[..., Any]


@dataclass(frozen=True)
class TaskPlugin:
    """Describes one task and its capabilities in the core runtime."""

    task_id: str
    name: str
    prompt_namespace: str
    capabilities: frozenset[str]
    constraints_model: type[BaseModel] | None = None
    record_model: type[BaseModel] | None = None
    task_runtime_model: type[BaseModel] | None = None
    validate_task_runtime: bool = False
    include_user_profile_in_prompt: bool = True
    build_runtime: BuildRuntimeFn | None = None
    action_handlers: Mapping[str, ActionHandlerFn] = field(default_factory=dict)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities
