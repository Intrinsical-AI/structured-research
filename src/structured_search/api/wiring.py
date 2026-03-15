"""Composition root: wires concrete infra adapters into application-layer ports."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    configure_dependencies,
)
from structured_search.application.core.plugins.gen_cv import GEN_CV_PLUGIN
from structured_search.application.core.plugins.job_search import JOB_SEARCH_PLUGIN
from structured_search.application.core.plugins.product_search import PRODUCT_SEARCH_PLUGIN
from structured_search.application.core.plugins.vuln_triage import VULN_TRIAGE_PLUGIN
from structured_search.application.core.task_registry import TaskRegistry, configure_task_registry
from structured_search.application.gen_cv.generate_cv import gen_cv
from structured_search.contracts import CandidateInput, GenCVResponse
from structured_search.domain.job_search.models import JobSearchConstraints
from structured_search.domain.product_search.models import ProductSearchConstraints
from structured_search.domain.vuln_triage.models import VulnTriageConstraints
from structured_search.infra.config_loader import task_json_to_scoring_config
from structured_search.infra.grounding import AtomsGrounding
from structured_search.infra.llm import MockLLM, build_llm
from structured_search.infra.loading import TolerantJSONLParser
from structured_search.infra.persistence_fs import (
    FilesystemProfileRepository,
    FilesystemRunRepository,
)
from structured_search.infra.prompts import PromptComposer
from structured_search.infra.scoring import HeuristicScorer
from structured_search.infra.vuln_triage_scoring import (
    VulnTriageScorer,
    vuln_task_json_to_scoring_config,
)
from structured_search.ports.grounding import GroundingPort
from structured_search.ports.prompting import PromptComposerPort

DEFAULT_PROFILES_BASE = Path("config")
DEFAULT_PROMPTS_DIR = Path("resources/prompts")
DEFAULT_RUNS_DIR = Path("runs")


def default_prompt_composer_factory(prompts_dir: Path) -> PromptComposerPort:
    return PromptComposer(prompts_dir)


def configure_filesystem_dependencies(
    *,
    profiles_base: Path = DEFAULT_PROFILES_BASE,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    prompts_dir: Path = DEFAULT_PROMPTS_DIR,
    prompt_composer_factory: Callable[
        [Path], PromptComposerPort
    ] = default_prompt_composer_factory,
) -> ApplicationDependencies:
    """Wire canonical filesystem adapters and set as active dependencies."""
    return configure_dependencies(
        profile_repo=FilesystemProfileRepository(base_dir=profiles_base),
        run_repo=FilesystemRunRepository(base_dir=runs_dir),
        prompts_dir=prompts_dir,
        jsonl_parser=TolerantJSONLParser(),
        prompt_composer_factory=prompt_composer_factory,
    )


# ---------------------------------------------------------------------------
# Plugin build_runtime factories (infra-backed)
# ---------------------------------------------------------------------------


def _job_search_build_runtime(constraints_payload: dict, task_payload: dict):
    constraints = JobSearchConstraints.model_validate(constraints_payload)
    scoring_config = task_json_to_scoring_config(task_payload)
    return constraints, HeuristicScorer(config=scoring_config)


def _product_search_build_runtime(constraints_payload: dict, task_payload: dict):
    constraints = ProductSearchConstraints.model_validate(constraints_payload)
    scoring_config = task_json_to_scoring_config(task_payload)
    return constraints, HeuristicScorer(config=scoring_config)


def _vuln_triage_build_runtime(constraints_payload: dict, task_payload: dict):
    constraints = VulnTriageConstraints.model_validate(constraints_payload)
    scoring_config = vuln_task_json_to_scoring_config(task_payload)
    return constraints, VulnTriageScorer(config=scoring_config)


# ---------------------------------------------------------------------------
# gen_cv action handler (infra-backed: build_llm, MockLLM, AtomsGrounding)
# ---------------------------------------------------------------------------


def _make_gen_cv_action_handler():
    from structured_search.application.common.dependencies import resolve_dependencies

    def _handler(
        *,
        profile_id: str,
        job: dict,
        candidate_profile: CandidateInput | dict,
        selected_claim_ids: list[str] | None = None,
        llm_model: str | None = None,
        allow_mock_fallback: bool = True,
        deps=None,
    ) -> GenCVResponse:
        resolved = resolve_dependencies(deps)
        atoms_dir = resolved.profile_repo.atoms_dir("gen_cv", profile_id)
        grounding: GroundingPort | None = (
            AtomsGrounding(atoms_dir=str(atoms_dir)) if atoms_dir.is_dir() else None
        )
        return gen_cv(
            task_id="gen_cv",
            profile_id=profile_id,
            job=job,
            candidate_profile=candidate_profile,
            selected_claim_ids=selected_claim_ids,
            llm_model=llm_model,
            allow_mock_fallback=allow_mock_fallback,
            deps=deps,
            build_llm_fn=build_llm,
            mock_llm_cls=MockLLM,
            grounding=grounding,
        )

    return _handler


# ---------------------------------------------------------------------------
# Wired plugin instances and registry
# ---------------------------------------------------------------------------


JOB_SEARCH_PLUGIN_WIRED = dataclasses.replace(
    JOB_SEARCH_PLUGIN, build_runtime=_job_search_build_runtime
)
PRODUCT_SEARCH_PLUGIN_WIRED = dataclasses.replace(
    PRODUCT_SEARCH_PLUGIN, build_runtime=_product_search_build_runtime
)
GEN_CV_PLUGIN_WIRED = dataclasses.replace(
    GEN_CV_PLUGIN, action_handlers={"gen-cv": _make_gen_cv_action_handler()}
)
VULN_TRIAGE_PLUGIN_WIRED = dataclasses.replace(
    VULN_TRIAGE_PLUGIN, build_runtime=_vuln_triage_build_runtime
)


def configure_wired_registry() -> TaskRegistry:
    """Build and configure the task registry with all infra-backed implementations."""
    registry = TaskRegistry(
        plugins={
            JOB_SEARCH_PLUGIN_WIRED.task_id: JOB_SEARCH_PLUGIN_WIRED,
            GEN_CV_PLUGIN_WIRED.task_id: GEN_CV_PLUGIN_WIRED,
            PRODUCT_SEARCH_PLUGIN_WIRED.task_id: PRODUCT_SEARCH_PLUGIN_WIRED,
            VULN_TRIAGE_PLUGIN_WIRED.task_id: VULN_TRIAGE_PLUGIN_WIRED,
        }
    )
    configure_task_registry(registry)
    return registry
