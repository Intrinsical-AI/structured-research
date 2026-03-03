"""Unit tests for application.job_search use-cases."""

from __future__ import annotations

from pathlib import Path

from structured_search.application.common.dependencies import ApplicationDependencies
from structured_search.application.job_search.ingest import ingest_validate_jsonl
from structured_search.application.job_search.profiles import (
    list_profiles,
    load_bundle,
    save_bundle,
)
from structured_search.application.job_search.prompts import generate_prompt
from structured_search.application.job_search.run_scoring import run_score, validate_run
from structured_search.contracts import ProfileBundle, RunScoreRequest
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.ports.persistence import BundleData, RunRepository, SnapshotWriteResult


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


def _minimal_bundle(profile_id: str = "app-profile") -> ProfileBundle:
    return ProfileBundle(
        profile_id=profile_id,
        constraints=_minimal_constraints(),
        task=_minimal_task(),
        task_config={"agent_name": "TEST"},
        user_profile={"name": "Test User"},
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


def test_profiles_bundle_roundtrip_and_listing(tmp_path: Path):
    deps = _deps(tmp_path)
    bundle = _minimal_bundle()
    result = save_bundle(bundle, deps=deps)
    assert result.valid is True

    loaded = load_bundle("app-profile", deps=deps)
    assert loaded.profile_id == "app-profile"
    assert loaded.constraints["domain"] == "job_search"

    discovered = list_profiles(deps=deps)
    assert any(item["id"] == "app-profile" for item in discovered)


def test_generate_prompt_includes_constraints_and_profile(tmp_path: Path):
    deps = _deps(tmp_path)
    save_bundle(_minimal_bundle(), deps=deps)

    prompt = generate_prompt("app-profile", "S3_execute", deps=deps)
    assert "## Search Constraints" in prompt.prompt
    assert "## Candidate Profile" in prompt.prompt


def test_ingest_validate_jsonl_reports_parse_errors():
    valid_line = (
        '{"id":"x","source":"test","company":"Acme","title":"Engineer",'
        '"posted_at":"2026-01-15","apply_url":"https://acme.example.com",'
        '"geo":{"region":"ES-MD","city":"Madrid","country":"Spain"},'
        '"modality":"remote","seniority":{"level":"senior"},"stack":["Python"],'
        '"evidence":[],"facts":[],"inferences":[],"anomalies":[],"incomplete":false}'
    )
    result = ingest_validate_jsonl(valid_line + "\nNOT_JSON")
    assert result.stats.parse_errors == 1
    assert result.stats.schema_ok == 1


def test_run_score_writes_snapshot(tmp_path: Path):
    deps = _deps(tmp_path)
    save_bundle(_minimal_bundle(profile_id="profile_1"), deps=deps)

    result = run_score(
        RunScoreRequest(
            profile_id="profile_1",
            records=[_minimal_posting_dict(1), _minimal_posting_dict(2)],
            require_snapshot=True,
        ),
        deps=deps,
    )

    assert result.run_id.startswith("profile_1-")
    assert result.snapshot_status == "written"
    assert result.snapshot_dir is not None


def test_validate_run_checks_snapshot_io_without_leaving_probe_files(tmp_path: Path):
    deps = _deps(tmp_path)
    save_bundle(_minimal_bundle(profile_id="profile_1"), deps=deps)

    result = validate_run(
        RunScoreRequest(
            profile_id="profile_1",
            records=[_minimal_posting_dict(1)],
            require_snapshot=True,
        ),
        deps=deps,
    )

    assert result.ok is True
    assert result.checks.snapshot_io_checked is True
    assert result.checks.snapshot_io_writable is True
    assert result.snapshot_probe_error is None
    assert list((tmp_path / "runs").glob("_validate-*")) == []


def test_validate_run_reports_not_runnable_when_required_snapshot_io_fails(tmp_path: Path):
    deps = ApplicationDependencies(
        profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
        run_repo=_FailingRunRepository(),
        prompts_dir=Path("resources/prompts"),
    )
    save_bundle(_minimal_bundle(profile_id="profile_1"), deps=deps)

    result = validate_run(
        RunScoreRequest(
            profile_id="profile_1",
            records=[_minimal_posting_dict(1)],
            require_snapshot=True,
        ),
        deps=deps,
    )

    assert result.ok is False
    assert result.checks.snapshot_io_checked is True
    assert result.checks.snapshot_io_writable is False
    assert result.snapshot_probe_error == "disk full"
