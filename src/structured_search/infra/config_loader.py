"""Config loader: maps task.json / task_config.json to runtime configs.

The task.json stores scoring gates and soft-scoring parameters in a human-
editable format. This module converts that
format to the SoftScoringConfig dataclasses used by HeuristicScorer so
the runtime config always reflects the profile config instead of hardcoded
defaults.
"""

from __future__ import annotations

import types as _types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from structured_search.domain.models import ConstraintRule
from structured_search.infra.scoring_config import (
    GatesConfig,
    PenaltiesConfig,
    SignalBoostConfig,
    SoftScoringConfig,
)

# ---------------------------------------------------------------------------
# Field-path introspection (used by save_bundle cross-field validation)
# ---------------------------------------------------------------------------


def _unwrap_to_model(ann: Any) -> type[BaseModel] | None:
    """Extract the first Pydantic model class from a type annotation.

    Handles direct models, ``Model | None`` (Python 3.10+ union), and
    ``Optional[Model]`` (typing.Union).  Ignores list/set/dict generics.
    """
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann

    origin = get_origin(ann)

    # typing.Union (covers Optional[X] = Union[X, None])
    if origin is Union:
        for arg in get_args(ann):
            if arg is type(None):
                continue
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg

    # Python 3.10+ X | Y syntax — get_origin returns types.UnionType
    if isinstance(ann, _types.UnionType):
        for arg in get_args(ann):
            if arg is type(None):
                continue
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg

    return None


def collect_model_field_paths(
    model_cls: type[BaseModel], prefix: str = "", max_depth: int = 3
) -> frozenset[str]:
    """Return all valid dotted field paths declared in a Pydantic v2 model.

    Recurses into nested Pydantic models (e.g. ``seniority.level``,
    ``geo.region``).  Does NOT recurse into ``list[str]``, plain scalars, or
    ``dict`` values.

    Useful for validating that constraint rule ``field`` paths actually exist
    on the target model before a search run.

    Args:
        model_cls: A Pydantic BaseModel subclass.
        prefix:    Dot-separated path prefix (used internally for recursion).
        max_depth: Maximum recursion depth (prevents infinite loops).

    Returns:
        Frozen set of valid dot-separated paths (e.g. ``{"seniority",
        "seniority.level", "geo", "geo.region", ...}``).
    """
    if max_depth <= 0:
        return frozenset()

    paths: set[str] = set()
    for name, field_info in model_cls.model_fields.items():
        full = f"{prefix}.{name}" if prefix else name
        paths.add(full)

        nested = _unwrap_to_model(field_info.annotation)
        if nested is not None:
            paths.update(collect_model_field_paths(nested, full, max_depth - 1))

    return frozenset(paths)


class TaskGatesInput(BaseModel):
    """Validated task.gates payload."""

    model_config = ConfigDict(extra="forbid")

    hard_filters_mode: Literal["require_any", "require_all"] = "require_all"
    hard_filters: list[ConstraintRule] = Field(default_factory=list)
    reject_anomalies: list[str] = Field(default_factory=list)
    required_evidence_fields: list[str] = Field(default_factory=list)


class TaskSignalBoostInput(BaseModel):
    """Validated task.soft_scoring.signal_boost payload."""

    model_config = ConfigDict(extra="allow")

    evidence_present: float = 0.0
    salary_disclosed: float = 0.0
    salary_field: str = "economics.salary_eur_gross"


class TaskPenaltiesInput(BaseModel):
    """Validated task.soft_scoring.penalties payload."""

    model_config = ConfigDict(extra="allow")

    incomplete: float = 0.0
    missing_salary: float = 0.0
    old_posting: float = 0.0
    old_posting_field: str = "recency.activity_age_days"
    old_posting_threshold_days: int = 30
    inference_used: float = 0.0
    prompt_injection_suspected: float = 0.0
    excess_hybrid_days: float = 0.0
    excess_hybrid_days_field: str = "onsite_days_per_week"
    excess_hybrid_days_threshold: int = 3


class TaskSoftScoringInput(BaseModel):
    """Validated task.soft_scoring payload."""

    model_config = ConfigDict(extra="allow")

    formula_version: str = "v2_soft_after_gates"
    prefer_weight_default: float = 1.0
    avoid_penalty_default: float = 1.0
    signal_boost: TaskSignalBoostInput = Field(default_factory=TaskSignalBoostInput)
    penalties: TaskPenaltiesInput = Field(default_factory=TaskPenaltiesInput)


class TaskRuntimeConfig(BaseModel):
    """Validated runtime-relevant task payload from bundle.task."""

    model_config = ConfigDict(extra="allow")

    gates: TaskGatesInput
    soft_scoring: TaskSoftScoringInput


def task_json_to_scoring_config(task: dict | TaskRuntimeConfig) -> SoftScoringConfig:
    """Convert a task.json dict to a SoftScoringConfig for HeuristicScorer.

    Only the ``gates`` and ``soft_scoring`` top-level keys are consumed;
    ``normalization``, ``dedupe``, etc. are ignored here.

    Args:
        task: Parsed task.json as a Python dict.

    Returns:
        SoftScoringConfig ready to pass to HeuristicScorer.
    """
    task_input = (
        task if isinstance(task, TaskRuntimeConfig) else TaskRuntimeConfig.model_validate(task)
    )

    gates = GatesConfig(
        hard_filters_mode=task_input.gates.hard_filters_mode,
        hard_filters=task_input.gates.hard_filters,
        reject_anomalies=task_input.gates.reject_anomalies,
        required_evidence_fields=task_input.gates.required_evidence_fields,
    )

    # --- signal boosts ---
    signal_boost_in = task_input.soft_scoring.signal_boost
    signal_boost = SignalBoostConfig(
        evidence_present=signal_boost_in.evidence_present,
        salary_disclosed=signal_boost_in.salary_disclosed,
        salary_field=signal_boost_in.salary_field,
    )

    # --- penalties ---
    penalties_in = task_input.soft_scoring.penalties
    penalties = PenaltiesConfig(
        incomplete=penalties_in.incomplete,
        missing_salary=penalties_in.missing_salary,
        old_posting=penalties_in.old_posting,
        old_posting_field=penalties_in.old_posting_field,
        old_posting_threshold_days=penalties_in.old_posting_threshold_days,
        inference_used=penalties_in.inference_used,
        prompt_injection_suspected=penalties_in.prompt_injection_suspected,
        excess_hybrid_days=penalties_in.excess_hybrid_days,
        excess_hybrid_days_field=penalties_in.excess_hybrid_days_field,
        excess_hybrid_days_threshold=penalties_in.excess_hybrid_days_threshold,
    )

    return SoftScoringConfig(
        formula_version=task_input.soft_scoring.formula_version,
        prefer_weight_default=task_input.soft_scoring.prefer_weight_default,
        avoid_penalty_default=task_input.soft_scoring.avoid_penalty_default,
        gates=gates,
        signal_boost=signal_boost,
        penalties=penalties,
    )
