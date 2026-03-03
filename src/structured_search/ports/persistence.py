"""Persistence ports for profile config bundles and run snapshots."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class ProfileRecord:
    """Profile listing entry returned by ProfileRepository.list_profiles."""

    id: str
    user_profile: dict[str, Any] | None
    updated_at: str


@dataclass(frozen=True)
class BundleData:
    """Raw bundle payload read/written by ProfileRepository."""

    constraints: dict[str, Any]
    task: dict[str, Any]
    task_config: dict[str, Any]
    user_profile: dict[str, Any] | None = None
    domain_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class SnapshotWriteResult:
    """Snapshot write result returned by RunRepository."""

    status: Literal["written", "failed"]
    snapshot_dir: str | None
    error: str | None = None


class ProfileRepository(ABC):
    """Port for profile bundle persistence."""

    @abstractmethod
    def list_profiles(self, task_id: str) -> list[ProfileRecord]:
        """Return discoverable profiles for one task."""
        raise NotImplementedError

    @abstractmethod
    def load_bundle(self, task_id: str, profile_id: str) -> BundleData:
        """Load a task/profile bundle by id."""
        raise NotImplementedError

    @abstractmethod
    def save_bundle(self, task_id: str, profile_id: str, bundle: BundleData) -> None:
        """Persist a task/profile bundle by id."""
        raise NotImplementedError

    @abstractmethod
    def atoms_dir(self, task_id: str, profile_id: str) -> Path:
        """Return atoms directory for one task/profile."""
        raise NotImplementedError


class RunRepository(ABC):
    """Port for run snapshot persistence."""

    @abstractmethod
    def save_snapshot(
        self,
        run_id: str,
        bundle: BundleData,
        input_records: list[dict[str, Any]],
        output_records: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> SnapshotWriteResult:
        """Persist a run snapshot and return write status."""
        raise NotImplementedError
