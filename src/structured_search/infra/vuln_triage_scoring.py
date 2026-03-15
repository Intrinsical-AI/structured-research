"""Clean scoring runtime for the vuln_triage task."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from structured_search.domain import BaseResult
from structured_search.infra.scoring import HeuristicScorer
from structured_search.infra.scoring_config import GatesConfig


class VulnTriageSignalBoostConfig(BaseModel):
    """Task-local boosts with vulnerability-specific semantics."""

    model_config = ConfigDict(extra="forbid")

    evidence_present: float = 0.0


class VulnTriagePenaltiesConfig(BaseModel):
    """Task-local penalties without job-search-specific naming."""

    model_config = ConfigDict(extra="forbid")

    incomplete: float = 0.0
    inference_used: float = 0.0
    prompt_injection_suspected: float = 0.0


class VulnTriageSoftScoringInput(BaseModel):
    """Validated task.soft_scoring payload for vuln_triage."""

    model_config = ConfigDict(extra="allow")

    formula_version: Literal["v2_soft_after_gates"] = "v2_soft_after_gates"
    prefer_weight_default: float = 1.0
    avoid_penalty_default: float = 1.0
    signal_boost: VulnTriageSignalBoostConfig = Field(default_factory=VulnTriageSignalBoostConfig)
    penalties: VulnTriagePenaltiesConfig = Field(default_factory=VulnTriagePenaltiesConfig)


class _VulnTriageRuntimeInput(BaseModel):
    """Validated runtime payload for vuln_triage bundles (infra-internal)."""

    model_config = ConfigDict(extra="allow")

    gates: GatesConfig
    soft_scoring: VulnTriageSoftScoringInput


class VulnTriageScoringConfig(BaseModel):
    """Normalized scoring config consumed by VulnTriageScorer."""

    model_config = ConfigDict(extra="forbid")

    formula_version: Literal["v2_soft_after_gates"] = "v2_soft_after_gates"
    prefer_weight_default: float = 1.0
    avoid_penalty_default: float = 1.0
    gates: GatesConfig = Field(default_factory=GatesConfig)
    signal_boost: VulnTriageSignalBoostConfig = Field(default_factory=VulnTriageSignalBoostConfig)
    penalties: VulnTriagePenaltiesConfig = Field(default_factory=VulnTriagePenaltiesConfig)


def vuln_task_json_to_scoring_config(
    task: dict[str, Any] | _VulnTriageRuntimeInput,
) -> VulnTriageScoringConfig:
    """Convert bundle.task payloads into a vuln_triage scoring config."""

    task_input = (
        task
        if isinstance(task, _VulnTriageRuntimeInput)
        else _VulnTriageRuntimeInput.model_validate(task)
    )
    ss = task_input.soft_scoring
    return VulnTriageScoringConfig(
        formula_version=ss.formula_version,
        prefer_weight_default=ss.prefer_weight_default,
        avoid_penalty_default=ss.avoid_penalty_default,
        gates=task_input.gates,
        signal_boost=ss.signal_boost,
        penalties=ss.penalties,
    )


class VulnTriageScorer(HeuristicScorer):
    """Heuristic scorer without job-search-specific soft-scoring semantics."""

    def __init__(self, config: VulnTriageScoringConfig):
        self.config = config

    def _compute_signal_adjustments(
        self, record: BaseResult, data: dict[str, Any]
    ) -> tuple[float, float]:
        del data
        boosts = self.config.signal_boost.evidence_present if record.evidence else 0.0
        return boosts, 0.0
