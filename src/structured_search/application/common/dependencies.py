"""Dependency wiring for application services."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.infra.prompts import PromptComposer
from structured_search.ports.persistence import ProfileRepository, RunRepository
from structured_search.ports.prompting import PromptComposerPort

DEFAULT_PROFILES_BASE = Path(os.getenv("PROFILES_BASE", "config"))
DEFAULT_PROMPTS_DIR = Path("resources/prompts")
DEFAULT_RUNS_DIR = Path("runs")


def default_prompt_composer_factory(prompts_dir: Path) -> PromptComposerPort:
    return PromptComposer(prompts_dir)


@dataclass(frozen=True)
class ApplicationDependencies:
    profile_repo: ProfileRepository
    run_repo: RunRepository
    prompts_dir: Path
    prompt_composer_factory: Callable[[Path], PromptComposerPort] = default_prompt_composer_factory


_ACTIVE_DEPS: ApplicationDependencies | None = None


_DEFAULT_DEPS = ApplicationDependencies(
    profile_repo=FilesystemProfileRepository(base_dir=DEFAULT_PROFILES_BASE),
    run_repo=FilesystemRunRepository(base_dir=DEFAULT_RUNS_DIR),
    prompts_dir=DEFAULT_PROMPTS_DIR,
)


def configure_dependencies(
    *,
    profile_repo: ProfileRepository | None = None,
    run_repo: RunRepository | None = None,
    prompts_dir: Path | None = None,
    prompt_composer_factory: Callable[[Path], PromptComposerPort] | None = None,
) -> ApplicationDependencies:
    """Set explicit application dependencies for runtime wiring."""
    global _ACTIVE_DEPS
    _ACTIVE_DEPS = ApplicationDependencies(
        profile_repo=profile_repo or _DEFAULT_DEPS.profile_repo,
        run_repo=run_repo or _DEFAULT_DEPS.run_repo,
        prompts_dir=prompts_dir or _DEFAULT_DEPS.prompts_dir,
        prompt_composer_factory=prompt_composer_factory or default_prompt_composer_factory,
    )
    return _ACTIVE_DEPS


def configure_filesystem_dependencies(
    *,
    profiles_base: Path = DEFAULT_PROFILES_BASE,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    prompts_dir: Path = DEFAULT_PROMPTS_DIR,
    prompt_composer_factory: Callable[
        [Path], PromptComposerPort
    ] = default_prompt_composer_factory,
) -> ApplicationDependencies:
    """Configure canonical filesystem adapters used by FastAPI startup."""
    return configure_dependencies(
        profile_repo=FilesystemProfileRepository(base_dir=profiles_base),
        run_repo=FilesystemRunRepository(base_dir=runs_dir),
        prompts_dir=prompts_dir,
        prompt_composer_factory=prompt_composer_factory,
    )


def clear_configured_dependencies() -> None:
    """Clear explicit runtime wiring and revert to defaults."""
    global _ACTIVE_DEPS
    _ACTIVE_DEPS = None


def resolve_dependencies(
    deps: ApplicationDependencies | None = None,
) -> ApplicationDependencies:
    """Resolve explicit dependencies or configured defaults."""
    if deps is not None:
        return deps
    if _ACTIVE_DEPS is not None:
        return _ACTIVE_DEPS
    return _DEFAULT_DEPS
