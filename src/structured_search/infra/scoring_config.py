"""Scoring configuration dataclasses for HeuristicScorer.

Separated from infra/scoring.py so config can be imported and composed
without pulling in the scorer implementation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from structured_search.domain import ConstraintRule


class GatesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard_filters_mode: Literal["require_all", "require_any"] = "require_all"
    """
    require_all → AND semantics: every hard filter must pass (each failure is a gate failure)
    require_any → OR semantics: gate fails only if ALL hard filters fail (at least one must pass)
    """
    hard_filters: list[ConstraintRule] = Field(default_factory=list)
    reject_anomalies: list[str] = Field(default_factory=list)
    required_evidence_fields: list[str] = Field(default_factory=list)


class SignalBoostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_present: float = 0.0
    salary_disclosed: float = 0.0
    salary_field: str = "economics.salary_eur_gross"


class ThresholdPenalty(BaseModel):
    """A penalty applied when a numeric field exceeds a threshold."""

    model_config = ConfigDict(extra="forbid")

    penalty: float = 0.0
    field: str
    threshold: int


class PenaltiesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incomplete: float = 0.0
    missing_salary: float = 0.0
    old_posting: ThresholdPenalty = Field(
        default_factory=lambda: ThresholdPenalty(field="recency.activity_age_days", threshold=30)
    )
    inference_used: float = 0.0
    prompt_injection_suspected: float = 0.0
    excess_hybrid_days: ThresholdPenalty = Field(
        default_factory=lambda: ThresholdPenalty(field="onsite_days_per_week", threshold=3)
    )


class SoftScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula_version: Literal["v2_soft_after_gates"] = "v2_soft_after_gates"
    prefer_weight_default: float = 1.0
    avoid_penalty_default: float = 1.0
    gates: GatesConfig = Field(default_factory=GatesConfig)
    signal_boost: SignalBoostConfig = Field(default_factory=SignalBoostConfig)
    penalties: PenaltiesConfig = Field(default_factory=PenaltiesConfig)
