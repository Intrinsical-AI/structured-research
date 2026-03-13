"""Filesystem adapters for persistence ports."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from structured_search.ports.persistence import (
    BundleData,
    ProfileRecord,
    ProfileRepository,
    RunRepository,
    SnapshotWriteResult,
)

logger = logging.getLogger(__name__)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class FilesystemProfileRepository(ProfileRepository):
    """ProfileRepository backed by config/<task_id>/<profile_id>/bundle.json."""

    _BUNDLE_FILENAME = "bundle.json"

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)

    @staticmethod
    def _validate_slug(kind: str, value: str) -> str:
        if not _SAFE_ID_RE.match(value):
            raise ValueError(f"Invalid {kind} {value!r}: allowed pattern is {_SAFE_ID_RE.pattern}")
        return value

    def _bundle_path(self, task_id: str, profile_id: str) -> Path:
        safe_task = self._validate_slug("task_id", task_id)
        safe_profile = self._validate_slug("profile_id", profile_id)
        return self.base_dir / safe_task / safe_profile / self._BUNDLE_FILENAME

    def _payload_to_bundle_data(
        self,
        profile_id: str,
        payload: dict[str, Any],
    ) -> BundleData:
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid bundle for profile {profile_id!r}: root must be an object")
        required = ("constraints", "task", "task_config")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Invalid bundle for profile {profile_id!r}: missing keys {missing}")
        for key in required:
            if not isinstance(payload[key], dict):
                raise ValueError(
                    f"Invalid bundle for profile {profile_id!r}: '{key}' must be an object"
                )
        for key in ("user_profile", "domain_schema", "result_schema"):
            value = payload.get(key)
            if value is not None and not isinstance(value, dict):
                raise ValueError(
                    f"Invalid bundle for profile {profile_id!r}: '{key}' must be object|null"
                )
        return BundleData(
            constraints=payload["constraints"],
            task=payload["task"],
            task_config=payload["task_config"],
            user_profile=payload.get("user_profile"),
            domain_schema=payload.get("domain_schema"),
            result_schema=payload.get("result_schema"),
        )

    def list_profiles(self, task_id: str = "job_search") -> list[ProfileRecord]:
        task_dir = self.base_dir / self._validate_slug("task_id", task_id)
        if not task_dir.exists():
            return []

        profiles: list[ProfileRecord] = []
        for profile_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            bundle_path = profile_dir / self._BUNDLE_FILENAME
            if not bundle_path.is_file():
                continue
            try:
                payload = _read_json(bundle_path)
                bundle = self._payload_to_bundle_data(profile_dir.name, payload)
            except Exception as e:
                logger.warning(
                    "Skipping invalid profile bundle '%s' at %s: %s",
                    profile_dir.name,
                    bundle_path,
                    e,
                )
                continue
            updated_at = datetime.fromtimestamp(bundle_path.stat().st_mtime).isoformat()
            profiles.append(
                ProfileRecord(
                    id=profile_dir.name,
                    user_profile=bundle.user_profile,
                    updated_at=updated_at,
                )
            )
        return profiles

    def load_bundle(
        self,
        task_id: str,
        profile_id: str,
    ) -> BundleData:
        bundle_path = self._bundle_path(task_id, profile_id)
        if not bundle_path.is_file():
            raise FileNotFoundError(
                f"Profile not found: task={task_id!r} profile={profile_id!r} "
                f"(expected {bundle_path})"
            )
        payload = _read_json(bundle_path)
        return self._payload_to_bundle_data(profile_id, payload)

    def save_bundle(
        self,
        task_id: str,
        profile_id: str,
        bundle: BundleData,
    ) -> None:
        payload = {
            "task_id": task_id,
            "profile_id": profile_id,
            "constraints": bundle.constraints,
            "task": bundle.task,
            "task_config": bundle.task_config,
            "user_profile": bundle.user_profile,
            "domain_schema": bundle.domain_schema,
            "result_schema": bundle.result_schema,
        }
        _write_json(self._bundle_path(task_id, profile_id), payload)

    def atoms_dir(self, task_id: str, profile_id: str) -> Path:
        safe_task = self._validate_slug("task_id", task_id)
        safe_profile = self._validate_slug("profile_id", profile_id)
        return self.base_dir / safe_task / safe_profile / "atoms"


class FilesystemRunRepository(RunRepository):
    """RunRepository backed by runs/* on disk."""

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)

    def save_snapshot(
        self,
        run_id: str,
        bundle: BundleData,
        input_records: list[dict[str, Any]],
        output_records: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> SnapshotWriteResult:
        snapshot_dir = self.base_dir / run_id
        try:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            _write_json(snapshot_dir / "constraints.json", bundle.constraints)
            _write_json(snapshot_dir / "task.json", bundle.task)
            _write_jsonl(snapshot_dir / "input.jsonl", input_records)
            _write_jsonl(snapshot_dir / "output.jsonl", output_records)
            _write_json(snapshot_dir / "summary.json", meta)
            return SnapshotWriteResult(
                status="written",
                snapshot_dir=str(snapshot_dir),
            )
        except Exception as e:
            return SnapshotWriteResult(
                status="failed",
                snapshot_dir=str(snapshot_dir),
                error=str(e),
            )
