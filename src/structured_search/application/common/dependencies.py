"""Dependency wiring for application services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from structured_search.ports.loading import JsonlTextParserPort
from structured_search.ports.persistence import ProfileRepository, RunRepository
from structured_search.ports.prompting import PromptComposerPort


@dataclass(frozen=True)
class ApplicationDependencies:
    profile_repo: ProfileRepository
    run_repo: RunRepository
    prompts_dir: Path
    jsonl_parser: JsonlTextParserPort
    prompt_composer_factory: Callable[[Path], PromptComposerPort] | None = None


_ACTIVE_DEPS: ApplicationDependencies | None = None


def configure_dependencies(
    *,
    profile_repo: ProfileRepository,
    run_repo: RunRepository,
    prompts_dir: Path,
    jsonl_parser: JsonlTextParserPort,
    prompt_composer_factory: Callable[[Path], PromptComposerPort] | None = None,
) -> ApplicationDependencies:
    """Set explicit application dependencies for runtime wiring."""
    global _ACTIVE_DEPS
    _ACTIVE_DEPS = ApplicationDependencies(
        profile_repo=profile_repo,
        run_repo=run_repo,
        prompts_dir=prompts_dir,
        jsonl_parser=jsonl_parser,
        prompt_composer_factory=prompt_composer_factory,
    )
    return _ACTIVE_DEPS


def clear_configured_dependencies() -> None:
    """Clear explicit runtime wiring."""
    global _ACTIVE_DEPS
    _ACTIVE_DEPS = None


def resolve_dependencies(
    deps: ApplicationDependencies | None = None,
) -> ApplicationDependencies:
    if deps is not None:
        return deps
    if _ACTIVE_DEPS is not None:
        return _ACTIVE_DEPS
    raise RuntimeError(
        "No application dependencies configured. "
        "Call configure_dependencies() or pass deps explicitly."
    )
