"""Unit tests for filesystem persistence adapters."""

from __future__ import annotations

import json
from pathlib import Path

from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.ports.persistence import BundleData


def _bundle_data() -> BundleData:
    return BundleData(
        constraints={"domain": "job_search", "must": [], "prefer": [], "avoid": []},
        task={"gates": {}, "soft_scoring": {}},
        task_config={"agent_name": "TEST"},
        user_profile={"name": "Jane"},
    )


def test_profile_repository_save_and_load_roundtrip(tmp_path):
    repo = FilesystemProfileRepository(base_dir=tmp_path)
    repo.save_bundle("job_search", "profile_test", _bundle_data())

    loaded = repo.load_bundle("job_search", "profile_test")
    assert loaded.constraints["domain"] == "job_search"
    assert loaded.task_config["agent_name"] == "TEST"
    assert loaded.user_profile == {"name": "Jane"}


def test_profile_repository_persists_optional_fields_as_none(tmp_path):
    repo = FilesystemProfileRepository(base_dir=tmp_path)
    bundle = _bundle_data()
    repo.save_bundle("job_search", "profile_test", bundle)

    bundle_path = tmp_path / "job_search" / "profile_test" / "bundle.json"
    assert json.loads(bundle_path.read_text())["user_profile"] == {"name": "Jane"}

    repo.save_bundle(
        "job_search",
        "profile_test",
        BundleData(
            constraints=bundle.constraints,
            task=bundle.task,
            task_config=bundle.task_config,
            user_profile=None,
            domain_schema=None,
            result_schema=None,
        ),
    )
    assert json.loads(bundle_path.read_text())["user_profile"] is None


def test_profile_repository_list_profiles_discovers_saved_profile(tmp_path):
    repo = FilesystemProfileRepository(base_dir=tmp_path)
    repo.save_bundle("job_search", "profile_test", _bundle_data())
    profiles = repo.list_profiles("job_search")
    assert len(profiles) == 1
    assert profiles[0].id == "profile_test"
    assert profiles[0].updated_at


def test_run_repository_writes_snapshot_files(tmp_path):
    repo = FilesystemRunRepository(base_dir=tmp_path / "runs")
    result = repo.save_snapshot(
        run_id="run-1",
        bundle=_bundle_data(),
        input_records=[{"id": "1"}],
        output_records=[{"id": "1", "score": 7.0}],
        meta={"run_id": "run-1"},
    )
    assert result.status == "written"
    snapshot_dir = Path(result.snapshot_dir or "")
    assert (snapshot_dir / "constraints.json").exists()
    assert (snapshot_dir / "task.json").exists()
    assert (snapshot_dir / "input.jsonl").exists()
    assert (snapshot_dir / "output.jsonl").exists()
    assert (snapshot_dir / "summary.json").exists()

    summary = json.loads((snapshot_dir / "summary.json").read_text())
    assert summary["run_id"] == "run-1"
