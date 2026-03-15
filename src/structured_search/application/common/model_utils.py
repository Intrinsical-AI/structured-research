"""Pydantic model introspection utilities (application layer)."""

from __future__ import annotations

import types as _types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel


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
