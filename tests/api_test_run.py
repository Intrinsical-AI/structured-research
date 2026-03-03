"""API-handler tests for POST /v1/job-search/run snapshot metadata and errors."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from structured_search.api.app import post_task_run, post_task_run_validate
from structured_search.contracts import (
    RunScoreRequest,
    RunSummary,
    RunValidateChecks,
    RunValidateSummary,
)


def test_run_response_includes_snapshot_metadata(monkeypatch):
    import structured_search.api.app as app_module

    def _fake_run_score(*, task_id: str, request: RunScoreRequest, plugin) -> RunSummary:
        assert task_id == "job_search"
        _ = request, plugin
        return RunSummary(
            run_id="profile_example-20260222-050500-a1b2c3",
            profile_id="profile_example",
            total=1,
            gate_passed=1,
            gate_failed=0,
            skipped=0,
            records=[
                {
                    "id": "1",
                    "company": "Acme",
                    "title": "Engineer",
                    "gate_passed": True,
                    "gate_failures": [],
                }
            ],
            errors=[],
            snapshot_dir="runs/profile_example-20260222-050500-a1b2c3",
            snapshot_status="written",
            snapshot_error=None,
        )

    monkeypatch.setattr(app_module, "run_score", _fake_run_score)
    response = post_task_run(
        "job_search",
        RunScoreRequest(
            profile_id="profile_example",
            records=[{"id": "1"}],
            require_snapshot=False,
        ),
    )
    assert response["snapshot_status"] == "written"
    assert response["snapshot_error"] is None
    assert isinstance(response["snapshot_dir"], str)
    assert response["metrics"]["gate_passed"] == 1
    assert response["metrics"]["gate_failed"] == 0
    assert response["metrics"]["gate_pass_rate"] == 1.0


def test_run_runtime_error_returns_500(monkeypatch):
    import structured_search.api.app as app_module

    def _boom(*, task_id: str, request: RunScoreRequest, plugin):
        _ = task_id, request, plugin
        raise RuntimeError("snapshot write failed")

    monkeypatch.setattr(app_module, "run_score", _boom)
    with pytest.raises(HTTPException) as exc:
        post_task_run(
            "job_search",
            RunScoreRequest(
                profile_id="profile_example",
                records=[{"id": "1"}],
                require_snapshot=True,
            ),
        )
    assert exc.value.status_code == 500
    assert "snapshot write failed" in str(exc.value.detail)


def test_run_value_error_returns_422(monkeypatch):
    import structured_search.api.app as app_module

    def _boom(*, task_id: str, request: RunScoreRequest, plugin):
        _ = task_id, request, plugin
        raise ValueError("invalid task payload")

    monkeypatch.setattr(app_module, "run_score", _boom)
    with pytest.raises(HTTPException) as exc:
        post_task_run(
            "job_search",
            RunScoreRequest(
                profile_id="profile_example",
                records=[{"id": "1"}],
                require_snapshot=False,
            ),
        )
    assert exc.value.status_code == 422
    assert "invalid task payload" in str(exc.value.detail)


def test_run_validation_error_returns_422(monkeypatch):
    import structured_search.api.app as app_module

    class _TmpModel(BaseModel):
        required_int: int

    def _boom(*, task_id: str, request: RunScoreRequest, plugin):
        _ = task_id, request, plugin
        _TmpModel.model_validate({"required_int": None})

    monkeypatch.setattr(app_module, "run_score", _boom)
    with pytest.raises(HTTPException) as exc:
        post_task_run(
            "job_search",
            RunScoreRequest(
                profile_id="profile_example",
                records=[{"id": "1"}],
                require_snapshot=False,
            ),
        )
    assert exc.value.status_code == 422


def test_run_validate_response_includes_snapshot_probe(monkeypatch):
    import structured_search.api.app as app_module

    def _fake_validate(*, task_id: str, request: RunScoreRequest, plugin) -> RunValidateSummary:
        assert task_id == "job_search"
        _ = request, plugin
        return RunValidateSummary(
            ok=True,
            profile_id="profile_example",
            total_records=1,
            valid_records=1,
            invalid_records=0,
            errors=[],
            checks=RunValidateChecks(
                profile_exists=True,
                constraints_valid=True,
                scoring_config_valid=True,
                all_records_schema_valid=True,
                snapshot_io_checked=True,
                snapshot_io_writable=True,
            ),
            snapshot_probe_dir="runs/_validate-profile_example-abcd1234",
            snapshot_probe_error=None,
        )

    monkeypatch.setattr(app_module, "validate_run", _fake_validate)
    response = post_task_run_validate(
        "job_search",
        RunScoreRequest(
            profile_id="profile_example",
            records=[{"id": "1"}],
            require_snapshot=True,
        ),
    )
    assert response.ok is True
    assert response.checks.snapshot_io_checked is True
    assert response.checks.snapshot_io_writable is True


def test_run_validate_missing_profile_returns_404(monkeypatch):
    import structured_search.api.app as app_module

    def _missing(*, task_id: str, request: RunScoreRequest, plugin):
        _ = task_id, request, plugin
        raise FileNotFoundError("Profile not found: profile_404")

    monkeypatch.setattr(app_module, "validate_run", _missing)
    with pytest.raises(HTTPException) as exc:
        post_task_run_validate(
            "job_search",
            RunScoreRequest(
                profile_id="profile_404",
                records=[{"id": "1"}],
                require_snapshot=False,
            ),
        )
    assert exc.value.status_code == 404


def test_run_validate_value_error_returns_422(monkeypatch):
    import structured_search.api.app as app_module

    def _boom(*, task_id: str, request: RunScoreRequest, plugin):
        _ = task_id, request, plugin
        raise ValueError("invalid task payload")

    monkeypatch.setattr(app_module, "validate_run", _boom)
    with pytest.raises(HTTPException) as exc:
        post_task_run_validate(
            "job_search",
            RunScoreRequest(
                profile_id="profile_example",
                records=[{"id": "1"}],
                require_snapshot=False,
            ),
        )
    assert exc.value.status_code == 422
