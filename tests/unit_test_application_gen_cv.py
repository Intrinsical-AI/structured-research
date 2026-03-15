"""Unit tests for application.gen_cv use-case orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from structured_search.application.common.dependencies import ApplicationDependencies
from structured_search.application.gen_cv.generate_cv import gen_cv
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.ports.persistence import BundleData


def _deps(tmp_path: Path) -> ApplicationDependencies:
    profile_repo = FilesystemProfileRepository(base_dir=tmp_path / "profiles")
    profile_repo.save_bundle(
        "gen_cv",
        "profile_example",
        BundleData(
            constraints={"domain": "gen_cv", "must": [], "prefer": [], "avoid": []},
            task={
                "gates": {
                    "hard_filters_mode": "require_all",
                    "hard_filters": [],
                    "reject_anomalies": [],
                    "required_evidence_fields": [],
                },
                "soft_scoring": {
                    "formula_version": "v2_soft_after_gates",
                    "prefer_weight_default": 1.0,
                    "avoid_penalty_default": 1.0,
                    "signal_boost": {},
                    "penalties": {},
                },
            },
            task_config={"runtime": {"llm": {"model": "mistral"}}},
            user_profile=None,
        ),
    )
    return ApplicationDependencies(
        profile_repo=profile_repo,
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=Path("resources/prompts"),
    )


def _job() -> dict:
    return {
        "id": "job-001",
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "stack": ["Python", "FastAPI"],
    }


def test_gen_cv_uses_fallback_when_llm_is_unavailable(tmp_path: Path, monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    def _boom(*_a, **_k):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(gen_cv_app, "build_llm", _boom)

    result = gen_cv(
        profile_id="profile_example",
        job=_job(),
        candidate_profile={"id": "cand-1", "seniority": "senior"},
        deps=_deps(tmp_path),
    )

    payload = result.model_dump(mode="json")
    assert payload["model_info"]["fallback_used"] is True
    assert payload["generated_cv_json"]["summary"]


def test_gen_cv_rejects_missing_seniority(tmp_path: Path):
    with pytest.raises(ValueError):
        gen_cv(
            profile_id="profile_example",
            job=_job(),
            candidate_profile={"id": "cand-1"},
            deps=_deps(tmp_path),
        )


def test_gen_cv_raises_when_mock_fallback_disabled(tmp_path: Path, monkeypatch):
    import structured_search.application.gen_cv.generate_cv as gen_cv_app

    def _boom(*_a, **_k):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(gen_cv_app, "build_llm", _boom)

    with pytest.raises(RuntimeError):
        gen_cv(
            profile_id="profile_example",
            job=_job(),
            candidate_profile={"id": "cand-1", "seniority": "senior"},
            allow_mock_fallback=False,
            deps=_deps(tmp_path),
        )
