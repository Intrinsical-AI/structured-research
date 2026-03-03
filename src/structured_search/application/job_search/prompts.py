"""Application use-case for prompt composition."""

from __future__ import annotations

import json

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.job_search.profiles import load_bundle
from structured_search.contracts import PromptResponse


def generate_prompt(
    profile_id: str,
    step: str = "S3_execute",
    deps: ApplicationDependencies | None = None,
) -> PromptResponse:
    """Compose extraction prompt and append profile constraints/profile payload."""
    resolved = resolve_dependencies(deps)
    bundle = load_bundle(profile_id, deps=resolved)
    composer = resolved.prompt_composer_factory(resolved.prompts_dir)
    prompt = composer.compose(task="job_search", step=step, profile=profile_id)

    sep = "\n\n" + "─" * 80 + "\n\n"

    constraints_json = json.dumps(bundle.constraints, indent=2, ensure_ascii=False)
    prompt += f"{sep}## Search Constraints\n\n```json\n{constraints_json}\n```"

    if bundle.user_profile:
        profile_json = json.dumps(bundle.user_profile, indent=2, ensure_ascii=False)
        prompt += f"{sep}## Candidate Profile\n\n```json\n{profile_json}\n```"

    return PromptResponse(profile_id=profile_id, step=step, prompt=prompt)
