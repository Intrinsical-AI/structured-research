"""Config loader: maps task.json / task_config.json to runtime configs.

The task.json stores scoring gates and soft-scoring parameters in a human-
editable format. This module converts that format to SoftScoringConfig used
by HeuristicScorer so the runtime config always reflects the profile config
instead of hardcoded defaults.
"""

from __future__ import annotations

import types as _types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

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


# ---------------------------------------------------------------------------
# Task runtime config — top-level parse target for bundle.task
# ---------------------------------------------------------------------------


class _TaskSoftScoringInput(BaseModel):
    """Validated task.soft_scoring payload.

    Uses scoring_config models directly; ``extra="allow"`` permits future
    top-level keys (e.g. normalization, dedupe) without breaking validation.
    """

    model_config = ConfigDict(extra="allow")

    formula_version: str = "v2_soft_after_gates"
    prefer_weight_default: float = 1.0
    avoid_penalty_default: float = 1.0
    signal_boost: SignalBoostConfig = Field(default_factory=SignalBoostConfig)
    penalties: PenaltiesConfig = Field(default_factory=PenaltiesConfig)


class TaskRuntimeConfig(BaseModel):
    """Validated runtime-relevant task payload from bundle.task."""

    model_config = ConfigDict(extra="allow")

    gates: GatesConfig
    soft_scoring: _TaskSoftScoringInput


def task_json_to_scoring_config(task: dict | TaskRuntimeConfig) -> SoftScoringConfig:
    """Convert a bundle.task dict to a SoftScoringConfig for HeuristicScorer.

    Only the ``gates`` and ``soft_scoring`` top-level keys are consumed;
    ``normalization``, ``dedupe``, etc. are ignored here.

    Args:
        task: Parsed task.json as a Python dict or already-validated TaskRuntimeConfig.

    Returns:
        SoftScoringConfig ready to pass to HeuristicScorer.
    """
    task_input = (
        task if isinstance(task, TaskRuntimeConfig) else TaskRuntimeConfig.model_validate(task)
    )
    ss = task_input.soft_scoring
    return SoftScoringConfig(
        formula_version=ss.formula_version,
        prefer_weight_default=ss.prefer_weight_default,
        avoid_penalty_default=ss.avoid_penalty_default,
        gates=task_input.gates,
        signal_boost=ss.signal_boost,
        penalties=ss.penalties,
    )
