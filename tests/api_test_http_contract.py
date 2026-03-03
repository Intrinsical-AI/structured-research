"""HTTP contract tests for API status-code mapping and payload shape."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from structured_search.api.app import post_gen_cv, post_run
from structured_search.contracts import GenCVRequest, RunScoreRequest, RunSummary


def test_post_gen_cv_missing_seniority_returns_422():
    with pytest.raises(HTTPException) as exc:
        post_gen_cv(
            GenCVRequest(
                profile_id="profile_1",
                job={
                    "id": "job-001",
                    "title": "Senior Backend Engineer",
                    "company": "Acme",
                    "stack": ["Python", "FastAPI"],
                },
                candidate_profile={"name": "Jane Doe", "seniority": ""},
            )
        )

    assert exc.value.status_code == 422
    assert "seniority" in str(exc.value.detail).lower()


def test_post_run_happy_path_via_http_contract(monkeypatch: pytest.MonkeyPatch):
    import structured_search.api.app as app_module

    def _fake_run_score(_request: RunScoreRequest) -> RunSummary:
        return RunSummary(
            run_id="profile_1-20260222-050500-a1b2c3",
            profile_id="profile_1",
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
            snapshot_dir="runs/profile_1-20260222-050500-a1b2c3",
            snapshot_status="written",
            snapshot_error=None,
        )

    monkeypatch.setattr(app_module, "run_score", _fake_run_score)
    body = post_run(
        RunScoreRequest(
            profile_id="profile_1",
            records=[{"id": "1"}],
        )
    )
    assert body["run_id"] == "profile_1-20260222-050500-a1b2c3"
    assert body["metrics"]["processed"] == 1
    assert body["snapshot_status"] == "written"


def test_post_run_runtime_error_maps_to_500(monkeypatch: pytest.MonkeyPatch):
    import structured_search.api.app as app_module

    def _boom(_request: RunScoreRequest) -> RunSummary:
        raise RuntimeError("snapshot write failed")

    monkeypatch.setattr(app_module, "run_score", _boom)
    with pytest.raises(HTTPException) as exc:
        post_run(
            RunScoreRequest(
                profile_id="profile_1",
                records=[{"id": "1"}],
                require_snapshot=True,
            )
        )

    assert exc.value.status_code == 500
    assert "snapshot write failed" in str(exc.value.detail)
