"""Dependency wiring tests for application layer runtime configuration."""

from __future__ import annotations

from pathlib import Path

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    clear_configured_dependencies,
    configure_dependencies,
)
from structured_search.application.job_search.profiles import (
    list_profiles,
    load_bundle,
    save_bundle,
)
from structured_search.contracts import ProfileBundle
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)


def _minimal_constraints() -> dict:
    return {
        "domain": "job_search",
        "must": [{"field": "modality", "op": "in", "value": ["remote", "hybrid"]}],
        "prefer": [],
        "avoid": [],
    }


def _minimal_task() -> dict:
    return {
        "gates": {
            "hard_filters_mode": "any",
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
    }


def _minimal_bundle(profile_id: str = "di-profile") -> ProfileBundle:
    return ProfileBundle(
        profile_id=profile_id,
        constraints=_minimal_constraints(),
        task=_minimal_task(),
        task_config={"agent_name": "TEST"},
        user_profile=None,
    )


def test_service_functions_accept_explicit_dependencies(tmp_path):
    deps = ApplicationDependencies(
        profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=Path("resources/prompts"),
    )

    result = save_bundle(_minimal_bundle(), deps=deps)
    assert result.valid is True

    loaded = load_bundle("di-profile", deps=deps)
    assert loaded.profile_id == "di-profile"

    profiles = list_profiles(deps=deps)
    assert any(item["id"] == "di-profile" for item in profiles)


def test_configure_dependencies_enables_injected_runtime_wiring(tmp_path):
    clear_configured_dependencies()
    configure_dependencies(
        profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=Path("resources/prompts"),
    )
    try:
        result = save_bundle(_minimal_bundle(profile_id="startup-profile"))
        assert result.valid is True

        loaded = load_bundle("startup-profile")
        assert loaded.profile_id == "startup-profile"
    finally:
        clear_configured_dependencies()
