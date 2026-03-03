"""Domain layer: pure, task-agnostic models and logic."""

from structured_search.domain.atoms import (
    ClaimAtom,
    ContextAtom,
    EvidenceAtom,
)
from structured_search.domain.models import (
    BaseConstraints,
    BaseResult,
    BaseUserProfile,
    ConstraintRule,
    EvidenceAnchor,
    EvidenceLocator,
    FactRecord,
    InferenceRecord,
    RelaxationPolicy,
    Sources,
)
from structured_search.domain.scoring import (
    ScoredResult,
    ScoringBreakdown,
)

__all__ = [
    "BaseConstraints",
    "BaseResult",
    "BaseUserProfile",
    "ClaimAtom",
    "ConstraintRule",
    "ContextAtom",
    "EvidenceAnchor",
    "EvidenceAtom",
    "EvidenceLocator",
    "FactRecord",
    "InferenceRecord",
    "RelaxationPolicy",
    "ScoredResult",
    "ScoringBreakdown",
    "Sources",
]
