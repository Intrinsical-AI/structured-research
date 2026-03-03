"""ScoringPort: interface for scoring implementations."""

from abc import ABC, abstractmethod

from structured_search.domain import BaseConstraints, BaseResult, ScoredResult


class ScoringPort(ABC):
    """Port for scoring records against constraints.

    Implementations handle:
    - Gate filtering (hard constraints)
    - Soft scoring (prefer/avoid rules)
    - Score normalization to [0, 10]
    """

    @abstractmethod
    def score(self, record: BaseResult, constraints: BaseConstraints) -> ScoredResult:
        """Score a record against constraints.

        Applies gates first, then soft scoring if gates pass.

        Args:
            record: Result record to score
            constraints: Constraint configuration

        Returns:
            ScoredResult with gate_passed, score, and breakdown
        """
        pass
