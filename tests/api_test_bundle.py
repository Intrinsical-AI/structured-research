"""Tests for bundle validation and run scoring using application-layer services."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from structured_search.application.common.dependencies import ApplicationDependencies
from structured_search.application.core.bundle_service import (
    list_profiles,
    load_bundle,
    save_bundle,
)
from structured_search.application.core.prompt_service import generate_prompt
from structured_search.application.core.run_service import run_score
from structured_search.application.core.task_registry import get_task_registry
from structured_search.contracts import ProfileBundle, RunScoreRequest
from structured_search.domain.job_search.models import JobPosting
from structured_search.infra.config_loader import collect_model_field_paths
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.ports.persistence import BundleData, RunRepository, SnapshotWriteResult

_TASK_ID = "job_search"
_PLUGIN = get_task_registry().get(_TASK_ID)
POSTING_VALID_PATHS = collect_model_field_paths(JobPosting)


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
    }


def _minimal_bundle(profile_id: str = "test-profile") -> ProfileBundle:
    return ProfileBundle(
        task_id=_TASK_ID,
        profile_id=profile_id,
        constraints=_minimal_constraints(),
        task=_minimal_task(),
        task_config={"agent_name": "TEST"},
        user_profile=None,
    )


def _minimal_posting_dict(idx: int = 1) -> dict:
    return {
        "id": f"test-{idx:03d}",
        "source": "test",
        "company": "Acme",
        "title": "Engineer",
        "posted_at": "2026-01-15",
        "apply_url": "https://acme.example.com/apply",
        "geo": {"region": "ES-MD", "city": "Madrid", "country": "Spain"},
        "modality": "remote",
        "seniority": {"level": "senior"},
        "stack": ["Python"],
        "evidence": [
            {
                "id": "e1",
                "field": "title",
                "quote": "Senior Engineer",
                "url": "https://acme.example.com/apply",
                "retrieved_at": "2026-01-15T10:00:00",
                "locator": {"type": "text_fragment", "value": "Senior Engineer"},
                "source_kind": "html",
            }
        ],
        "facts": [{"field": "title", "value": "Engineer", "evidence_ids": ["e1"]}],
        "inferences": [],
        "anomalies": [],
        "incomplete": False,
    }


def _deps(tmp_path: Path) -> ApplicationDependencies:
    return ApplicationDependencies(
        profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=Path("resources/prompts"),
    )


class _FailingRunRepository(RunRepository):
    def save_snapshot(
        self,
        run_id: str,
        bundle: BundleData,
        input_records: list[dict],
        output_records: list[dict],
        meta: dict,
    ) -> SnapshotWriteResult:
        return SnapshotWriteResult(
            status="failed",
            snapshot_dir=f"runs/{run_id}",
            error="disk full",
        )


class TestCollectModelFieldPaths:
    def test_top_level_fields_present(self):
        paths = collect_model_field_paths(JobPosting)
        for field in ("modality", "seniority", "geo", "stack", "apply_url", "posted_at"):
            assert field in paths

    def test_nested_fields_present(self):
        paths = collect_model_field_paths(JobPosting)
        assert "seniority.level" in paths
        assert "geo.region" in paths
        assert "geo.city" in paths
        assert "geo.country" in paths

    def test_deeply_nested_fields_present(self):
        paths = collect_model_field_paths(JobPosting)
        assert "economics.salary_eur_gross" in paths
        assert "recency.activity_age_days" in paths
        assert "domain.tags" in paths

    def test_unknown_path_not_present(self):
        paths = collect_model_field_paths(JobPosting)
        assert "nonexistent_field" not in paths
        assert "geo.nonexistent" not in paths

    def test_module_level_constant_matches(self):
        fresh = collect_model_field_paths(JobPosting)
        assert fresh == POSTING_VALID_PATHS


class TestSaveBundle:
    def test_valid_bundle_is_saved(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle()
        bundle_path = tmp_path / "profiles" / "job_search" / bundle.profile_id / "bundle.json"
        result = save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.valid is True
        assert bundle_path.exists()
        saved = json.loads(bundle_path.read_text())
        assert "constraints" in saved
        assert "task" in saved
        assert "task_config" in saved

    def test_user_profile_written_when_present(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle()
        bundle.user_profile = {"timezone": "Europe/Madrid", "mobility": "local"}
        bundle_path = tmp_path / "profiles" / "job_search" / bundle.profile_id / "bundle.json"
        result = save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.valid is True
        assert json.loads(bundle_path.read_text())["user_profile"] == bundle.user_profile

    def test_unknown_field_path_produces_warning_not_error(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle()
        bundle.constraints["must"].append(
            {"field": "totally_fake_field", "op": "=", "value": True}
        )
        result = save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.valid is True
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert warnings[0].code == "unknown_field_path"

    def test_invalid_constraints_schema_blocks_save(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle()
        bundle.constraints["must"] = [{"field": "modality", "op": "INVALID_OP", "value": "remote"}]
        bundle_path = tmp_path / "profiles" / "job_search" / bundle.profile_id / "bundle.json"

        result = save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.valid is False
        assert not bundle_path.exists()

    def test_legacy_must_pass_constraints_must_field_is_rejected(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle()
        gates = bundle.task.get("gates", {})
        assert isinstance(gates, dict)
        gates["must_pass_constraints_must"] = False

        result = save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.valid is False
        assert any("must_pass_constraints_must" in i.path for i in result.issues)


class TestRunScore:
    def _make_request(self, profile_id: str = "profile_example") -> RunScoreRequest:
        return RunScoreRequest(
            profile_id=profile_id,
            records=[_minimal_posting_dict(1), _minimal_posting_dict(2)],
        )

    def test_returns_run_id_and_snapshot(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle(profile_id="profile_example")
        save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        result = run_score(
            task_id=_TASK_ID,
            request=self._make_request("profile_example"),
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.run_id.startswith("job_search-profile_example-")
        assert result.snapshot_status == "written"
        snapshot_dir = Path(result.snapshot_dir or "")
        assert (snapshot_dir / "constraints.json").exists()
        assert (snapshot_dir / "task.json").exists()
        assert (snapshot_dir / "input.jsonl").exists()
        assert (snapshot_dir / "output.jsonl").exists()
        assert (snapshot_dir / "summary.json").exists()

    def test_gate_counts_reflect_config(self, tmp_path):
        deps = _deps(tmp_path)
        bundle = _minimal_bundle(profile_id="profile_example")
        save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        result = run_score(
            task_id=_TASK_ID,
            request=self._make_request("profile_example"),
            plugin=_PLUGIN,
            deps=deps,
        )

        assert result.total == 2
        assert result.skipped == 0
        assert result.gate_passed == 2
        assert result.gate_failed == 0

    def test_require_snapshot_true_raises_when_snapshot_write_fails(self, tmp_path):
        deps = ApplicationDependencies(
            profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
            run_repo=_FailingRunRepository(),
            prompts_dir=Path("resources/prompts"),
        )
        bundle = _minimal_bundle(profile_id="profile_example")
        save_bundle(
            task_id=_TASK_ID,
            profile_id=bundle.profile_id,
            bundle=bundle,
            plugin=_PLUGIN,
            deps=deps,
        )

        request = RunScoreRequest(
            profile_id="profile_example",
            records=[_minimal_posting_dict(1)],
            require_snapshot=True,
        )
        with pytest.raises(RuntimeError):
            run_score(task_id=_TASK_ID, request=request, plugin=_PLUGIN, deps=deps)


@pytest.mark.integration
def test_load_bundle_profile_example():
    bundle = load_bundle(task_id=_TASK_ID, profile_id="profile_example")
    assert bundle.profile_id == "profile_example"
    assert "must" in bundle.constraints
    assert "gates" in bundle.task


@pytest.mark.integration
def test_save_bundle_roundtrip_profile_example(tmp_path):
    deps = _deps(tmp_path)
    original = load_bundle(task_id=_TASK_ID, profile_id="profile_example")
    result = save_bundle(
        task_id=_TASK_ID,
        profile_id=original.profile_id,
        bundle=original,
        plugin=_PLUGIN,
        deps=deps,
    )

    assert result.valid is True
    written = json.loads(
        (tmp_path / "profiles" / "job_search" / original.profile_id / "bundle.json").read_text()
    )
    assert written["constraints"]["domain"] == original.constraints["domain"]


@pytest.mark.integration
def test_load_bundle_profile_example_includes_optional_schemas():
    bundle = load_bundle(task_id=_TASK_ID, profile_id="profile_example")
    assert bundle.domain_schema is None or isinstance(bundle.domain_schema, dict)
    assert bundle.result_schema is None or isinstance(bundle.result_schema, dict)


@pytest.mark.integration
def test_load_bundle_without_optional_schemas_keeps_none(tmp_path):
    deps = _deps(tmp_path)
    profile_id = "profile_without_optional_schemas"
    bundle = _minimal_bundle(profile_id=profile_id)
    save_result = save_bundle(
        task_id=_TASK_ID,
        profile_id=profile_id,
        bundle=bundle,
        plugin=_PLUGIN,
        deps=deps,
    )

    assert save_result.valid is True

    bundle = load_bundle(task_id=_TASK_ID, profile_id=profile_id, deps=deps)
    assert bundle.domain_schema is None
    assert bundle.result_schema is None


@pytest.mark.integration
def test_list_profiles_discovers_profile_example_and_profile_example():
    profiles = list_profiles(task_id=_TASK_ID)
    ids = {p["id"] for p in profiles}
    assert "profile_example" in ids
    assert "profile_example" in ids


@pytest.mark.integration
def test_generate_prompt_embeds_candidate_profile_section():
    prompt = generate_prompt(
        task_id=_TASK_ID,
        profile_id="profile_example",
        step="S3_execute",
        plugin=_PLUGIN,
    ).prompt
    assert "## Search Constraints" in prompt
    assert "## Candidate Profile" in prompt
