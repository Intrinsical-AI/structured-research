"""Application use-case for CV generation orchestration and fallback policy."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.gen_cv.service import GenCVService
from structured_search.contracts import CandidateInput, GenCVResponse
from structured_search.domain.gen_cv.models import (
    CandidateAtomsProfile,
    GeneratedCV,
    JobDescription,
)
from structured_search.infra.grounding import AtomsGrounding
from structured_search.infra.llm import MockLLM, build_llm
from structured_search.ports.grounding import GroundingPort
from structured_search.ports.llm import LLMPort

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^\s*(no\s+data(\s+provided|\s+available)?|n/?a)\s*[\.\!\?]*\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(not\s+available|not\s+provided|unknown|null|none)\s*[\.\!\?]*\s*$",
        re.IGNORECASE,
    ),
)


class _EmptyGrounding(GroundingPort):
    """Fallback grounding adapter when atoms are unavailable."""

    def get_context(self, domain: str):
        return []

    def get_claims_by_context(self, context_id: str):
        return []

    def get_evidence(self, evidence_id: str):
        return None


def _coerce_seniority(value: str | None) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("candidate_profile.seniority is required and must be a non-empty string")


def _coerce_job_seniority(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        first = next((x for x in value if isinstance(x, str) and x.strip()), None)
        if first:
            return first.strip()
    if isinstance(value, dict):
        level = value.get("level")
        if isinstance(level, str) and level.strip():
            return level.strip()
    return None


def _job_input_to_description(job: dict[str, Any]) -> JobDescription:
    payload = dict(job)
    payload["seniority"] = _coerce_job_seniority(payload.get("seniority"))
    return JobDescription.model_validate(payload)


def _candidate_input_to_profile(
    profile_id: str,
    candidate: CandidateInput,
) -> CandidateAtomsProfile:
    seniority = _coerce_seniority(candidate.seniority)

    tech_stack: dict[str, list[str]]
    if candidate.tech_stack is None:
        tech_stack = {"languages": [], "frameworks": [], "platforms": [], "domains": []}
    else:
        tech_stack = candidate.tech_stack.model_dump(mode="json")

    spoken_languages = candidate.spoken_languages
    availability_days = 30 if candidate.availability_days is None else candidate.availability_days
    profile_payload = {
        "id": candidate.id or f"{profile_id}_candidate",
        "name": candidate.name,
        "seniority": seniority,
        "tech_stack": tech_stack,
        "experience": [e.model_dump(mode="json") for e in candidate.experience],
        "education": candidate.education,
        "spoken_languages": spoken_languages,
        "location": candidate.location,
        "timezone": candidate.timezone,
        "availability_days": availability_days,
    }
    return CandidateAtomsProfile.model_validate(profile_payload)


def _render_cv_markdown(cv_data: dict[str, Any]) -> str:
    title = cv_data.get("title") or "Generated CV"
    summary = cv_data.get("summary") or ""
    highlights = cv_data.get("highlights") or []
    lines = [f"# {title}", "", "## Summary", "", str(summary), ""]
    if isinstance(highlights, list) and highlights:
        lines.extend(["## Highlights", ""])
        lines.extend(f"- {h}" for h in highlights)
        lines.append("")
    grounded = cv_data.get("grounded_claim_ids") or []
    if isinstance(grounded, list):
        lines.extend(
            [
                "## Grounded Claims",
                "",
                ", ".join(str(x) for x in grounded) or "(none)",
                "",
            ]
        )
    return "\n".join(lines)


def _has_meaningful_cv_content(cv: GeneratedCV) -> bool:
    def _is_placeholder(value: str) -> bool:
        return any(pattern.match(value) for pattern in _PLACEHOLDER_PATTERNS)

    summary_ok = (
        isinstance(cv.summary, str)
        and bool(cv.summary.strip())
        and not _is_placeholder(cv.summary)
    )
    highlights_ok = any(
        isinstance(item, str) and bool(item.strip()) and not _is_placeholder(item)
        for item in cv.highlights
    )
    return summary_ok or highlights_ok


def _as_non_empty_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _task_config_llm_model(task_config: dict[str, Any]) -> str | None:
    runtime = task_config.get("runtime")
    if not isinstance(runtime, dict):
        return None
    llm_cfg = runtime.get("llm")
    if not isinstance(llm_cfg, dict):
        return None
    return _as_non_empty_str(llm_cfg.get("model"))


def _task_config_llm_provider(task_config: dict[str, Any]) -> str | None:
    runtime = task_config.get("runtime")
    if not isinstance(runtime, dict):
        return None
    llm_cfg = runtime.get("llm")
    if not isinstance(llm_cfg, dict):
        return None
    return _as_non_empty_str(llm_cfg.get("provider"))


def _resolve_gen_cv_model_name(
    requested_model: str | None, task_config: dict[str, Any]
) -> str | None:
    return (
        _as_non_empty_str(requested_model)
        or _as_non_empty_str(os.getenv("STRUCTURED_SEARCH_LLM_MODEL"))
        or _task_config_llm_model(task_config)
    )


def _resolve_gen_cv_provider(task_config: dict[str, Any]) -> str:
    return (
        _as_non_empty_str(os.getenv("STRUCTURED_SEARCH_LLM_PROVIDER"))
        or _task_config_llm_provider(task_config)
        or "ollama"
    )


def _build_mock_cv_llm(
    *,
    mock_llm_cls: type[MockLLM],
    job_model: JobDescription,
    candidate_model: CandidateAtomsProfile,
    selected_claim_ids: list[str] | None,
) -> MockLLM:
    return mock_llm_cls(
        json_response={
            "summary": (
                f"{candidate_model.seniority.capitalize()} candidate aligned to "
                f"{job_model.title} at {job_model.company}."
            ),
            "highlights": [
                "Profile generated in fallback mode (no LLM available).",
                "Review and regenerate with a configured LLM for production quality.",
            ],
            "cited_claim_ids": selected_claim_ids or [],
        }
    )


def gen_cv(
    *,
    task_id: str = "gen_cv",
    profile_id: str,
    job: dict[str, Any],
    candidate_profile: CandidateInput | dict[str, Any],
    selected_claim_ids: list[str] | None = None,
    llm_model: str | None = None,
    allow_mock_fallback: bool = True,
    deps: ApplicationDependencies | None = None,
    llm: LLMPort | None = None,
    mock_llm_cls: type[MockLLM] | None = None,
    gen_cv_service_cls: type[GenCVService] | None = None,
) -> GenCVResponse:
    """Generate CV markdown+JSON using a configured LLM with deterministic mock fallback.

    Args:
        llm: Pre-built LLMPort instance. When provided, skips provider/model resolution
             (useful for tests or when the caller manages the LLM lifecycle).
    """
    resolved = resolve_dependencies(deps)
    mock_llm_cls = mock_llm_cls or MockLLM
    gen_cv_service_cls = gen_cv_service_cls or GenCVService
    bundle = resolved.profile_repo.load_bundle(task_id, profile_id)

    job_model = _job_input_to_description(job)
    candidate_input = (
        candidate_profile
        if isinstance(candidate_profile, CandidateInput)
        else CandidateInput.model_validate(candidate_profile)
    )
    candidate_model = _candidate_input_to_profile(profile_id, candidate_input)

    atoms_dir = resolved.profile_repo.atoms_dir(task_id, profile_id)
    grounding: GroundingPort = (
        AtomsGrounding(atoms_dir=str(atoms_dir)) if atoms_dir.is_dir() else _EmptyGrounding()
    )

    provider = _resolve_gen_cv_provider(bundle.task_config)
    model_name = _resolve_gen_cv_model_name(llm_model, bundle.task_config)

    fallback_used = False
    active_llm: LLMPort
    if llm is not None:
        active_llm = llm
    else:
        try:
            active_llm = build_llm(provider, model_name)
        except Exception as exc:
            if not allow_mock_fallback:
                raise RuntimeError(
                    "LLM unavailable and mock fallback disabled: "
                    f"provider={provider}, model={model_name}, error={exc}"
                ) from exc
            logger.warning("LLM unavailable, using MockLLM fallback: %s", exc)
            active_llm = _build_mock_cv_llm(
                mock_llm_cls=mock_llm_cls,
                job_model=job_model,
                candidate_model=candidate_model,
                selected_claim_ids=selected_claim_ids,
            )
            fallback_used = True

    prompt_composer = (
        resolved.prompt_composer_factory(resolved.prompts_dir)
        if resolved.prompts_dir.exists()
        else None
    )

    def _generate_with_llm(active: LLMPort) -> GeneratedCV:
        return gen_cv_service_cls(
            llm=active,
            grounding=grounding,
            prompt_composer=prompt_composer,
        ).generate(
            job=job_model,
            candidate=candidate_model,
            allowed_claim_ids=selected_claim_ids,
        )

    try:
        cv = _generate_with_llm(active_llm)
        if not _has_meaningful_cv_content(cv):
            raise RuntimeError("CV generation returned empty summary/highlights content")
    except Exception as exc:
        if not allow_mock_fallback or fallback_used:
            raise RuntimeError(
                "CV generation failed and mock fallback disabled: "
                f"provider={provider}, model={model_name}, error={exc}"
            ) from exc
        logger.warning(
            "LLM generation failed, retrying with MockLLM fallback: "
            "provider=%s, model=%s, error=%s",
            provider,
            model_name,
            exc,
        )
        active_llm = _build_mock_cv_llm(
            mock_llm_cls=mock_llm_cls,
            job_model=job_model,
            candidate_model=candidate_model,
            selected_claim_ids=selected_claim_ids,
        )
        fallback_used = True
        try:
            cv = _generate_with_llm(active_llm)
        except Exception as fallback_error:
            raise RuntimeError(
                "CV generation failed even with mock fallback: "
                f"provider={provider}, model={model_name}, error={fallback_error}"
            ) from fallback_error

    cv_json = cv.model_dump(mode="json")
    markdown = _render_cv_markdown(cv_json)

    return GenCVResponse(
        cv_markdown=markdown,
        generated_cv_json=cv_json,
        model_info={
            "model": cv_json.get("model_used") or getattr(active_llm, "model", "mock"),
            "provider": provider if not fallback_used else "mock",
            "grounded_claim_count": len(cv_json.get("grounded_claim_ids") or []),
            "profile_id": profile_id,
            "markdown_hash": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "fallback_used": fallback_used,
        },
    )
