"""Unit tests for run_service precondition invariants."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from structured_search.application.core.run_service import run_score, validate_run
from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.contracts import RunScoreRequest


class _AnyModel(BaseModel):
    pass


def _build_runtime_stub(constraints, task):
    raise NotImplementedError


def _plugin_without_runtime() -> TaskPlugin:
    """A plugin that declares no scoring capability (build_runtime=None)."""
    return TaskPlugin(
        task_id="no_runtime_task",
        name="No Runtime Task",
        prompt_namespace="no_runtime_task",
        capabilities=frozenset({"prompt"}),
        build_runtime=None,
        record_model=None,
    )


def _plugin_runtime_only() -> TaskPlugin:
    """build_runtime set but record_model=None."""
    return TaskPlugin(
        task_id="runtime_only_task",
        name="Runtime Only Task",
        prompt_namespace="runtime_only_task",
        capabilities=frozenset({"score"}),
        build_runtime=_build_runtime_stub,
        record_model=None,
    )


def _plugin_model_only() -> TaskPlugin:
    """record_model set but build_runtime=None."""
    return TaskPlugin(
        task_id="model_only_task",
        name="Model Only Task",
        prompt_namespace="model_only_task",
        capabilities=frozenset({"score"}),
        build_runtime=None,
        record_model=_AnyModel,
    )


def _request() -> RunScoreRequest:
    return RunScoreRequest(
        profile_id="profile_1",
        records=[{"id": "r1"}],
        require_snapshot=False,
    )


def test_run_score_raises_for_plugin_without_build_runtime():
    with pytest.raises(ValueError, match="does not support scoring runtime"):
        run_score(
            task_id="no_runtime_task",
            request=_request(),
            plugin=_plugin_without_runtime(),
        )


def test_validate_run_raises_for_plugin_without_build_runtime():
    with pytest.raises(ValueError, match="does not support scoring runtime"):
        validate_run(
            task_id="no_runtime_task",
            request=_request(),
            plugin=_plugin_without_runtime(),
        )


def test_run_score_raises_when_build_runtime_missing_but_record_model_set():
    with pytest.raises(ValueError, match="does not support scoring runtime"):
        run_score(
            task_id="model_only_task",
            request=_request(),
            plugin=_plugin_model_only(),
        )


def test_run_score_raises_when_record_model_missing_but_build_runtime_set():
    with pytest.raises(ValueError, match="does not support scoring runtime"):
        run_score(
            task_id="runtime_only_task",
            request=_request(),
            plugin=_plugin_runtime_only(),
        )
