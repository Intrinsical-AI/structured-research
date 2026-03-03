"""Generic prompt composition service for task plugins."""

from __future__ import annotations

import json

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.core.bundle_service import load_bundle
from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.contracts import PromptResponse


def generate_prompt(
    *,
    task_id: str,
    profile_id: str,
    step: str,
    plugin: TaskPlugin,
    deps: ApplicationDependencies | None = None,
) -> PromptResponse:
    resolved = resolve_dependencies(deps)
    bundle = load_bundle(task_id=task_id, profile_id=profile_id, deps=resolved)
    composer = resolved.prompt_composer_factory(resolved.prompts_dir)
    prompt = composer.compose(task=plugin.prompt_namespace, step=step, profile=profile_id)

    sep = "\n\n" + "─" * 80 + "\n\n"
    constraints_json = json.dumps(bundle.constraints, indent=2, ensure_ascii=False)
    prompt += f"{sep}## Search Constraints\n\n```json\n{constraints_json}\n```"

    if plugin.include_user_profile_in_prompt and bundle.user_profile:
        profile_json = json.dumps(bundle.user_profile, indent=2, ensure_ascii=False)
        prompt += f"{sep}## Candidate Profile\n\n```json\n{profile_json}\n```"

    return PromptResponse(profile_id=profile_id, step=step, prompt=prompt)
