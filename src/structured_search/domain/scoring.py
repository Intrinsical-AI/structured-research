"""Scoring result models: ScoredResult and ScoringBreakdown.

Separated from domain/models.py to keep pure domain invariants distinct
from scoring output types.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from structured_search.domain.models import BaseResult


class ScoringBreakdown(BaseModel):
    """Breakdown of score calculation."""

    base: float = Field(..., description="Base score from prefer/avoid")
    boosts: float = Field(..., description="Boosts added to score")
    avoid_penalty: float = Field(..., description="Penalty from avoid rules")
    penalties: float = Field(..., description="Penalties applied")
    raw_score: float = Field(..., description="Raw score before clamping")
    final_score: float = Field(..., description="Final score [0,10]")


class ScoredResult(BaseResult):
    """Result after gates and scoring.

    Extends BaseResult with scoring information.
    Task-specific scored results inherit from both TaskResult and ScoredResult.
    """

    gate_passed: bool = Field(..., description="Did record pass all gates?")
    gate_failures: list[str] = Field(default_factory=list, description="Gate failure reasons")
    score: float | None = Field(None, description="Final score [0,10], None if gates failed")
    score_breakdown: ScoringBreakdown | None = Field(
        None, description="Score calculation breakdown"
    )
