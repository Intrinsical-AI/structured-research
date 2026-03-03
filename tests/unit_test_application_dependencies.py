"""Unit tests for application dependency wiring."""

from __future__ import annotations

from pathlib import Path

from structured_search.application.common.dependencies import (
    clear_configured_dependencies,
    configure_dependencies,
    configure_filesystem_dependencies,
    resolve_dependencies,
)
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)


def test_configure_dependencies_overrides_runtime_wiring(tmp_path: Path):
    clear_configured_dependencies()
    configured = configure_dependencies(
        profile_repo=FilesystemProfileRepository(base_dir=tmp_path / "profiles"),
        run_repo=FilesystemRunRepository(base_dir=tmp_path / "runs"),
        prompts_dir=tmp_path / "prompts",
    )
    try:
        resolved = resolve_dependencies()
        assert resolved == configured
        assert resolved.prompts_dir == tmp_path / "prompts"
    finally:
        clear_configured_dependencies()


def test_configure_filesystem_dependencies_uses_expected_paths(tmp_path: Path):
    clear_configured_dependencies()
    try:
        resolved = configure_filesystem_dependencies(
            profiles_base=tmp_path / "profiles",
            runs_dir=tmp_path / "runs",
            prompts_dir=tmp_path / "prompts",
        )
        assert isinstance(resolved.profile_repo, FilesystemProfileRepository)
        assert isinstance(resolved.run_repo, FilesystemRunRepository)
        assert resolved.prompts_dir == tmp_path / "prompts"
    finally:
        clear_configured_dependencies()
