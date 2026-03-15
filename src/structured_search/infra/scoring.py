"""Scoring adapters: HeuristicScorer, MockScorer."""

from __future__ import annotations

import logging
from typing import Any

from structured_search.domain import (
    BaseConstraints,
    BaseResult,
    ConstraintRule,
    ScoredResult,
    ScoringBreakdown,
)
from structured_search.infra.scoring_config import SoftScoringConfig
from structured_search.ports.scoring import ScoringPort

logger = logging.getLogger(__name__)

_PROMPT_INJECTION_ANOMALY = "prompt_injection_suspected"
_MISSING = object()  # sentinel: key absent from dict (distinct from explicit null)

__all__ = [
    "HeuristicScorer",
    "MockScorer",
]


# ============================================================================
# HeuristicScorer
# ============================================================================


class HeuristicScorer(ScoringPort):
    """Two-stage scorer: gates (hard) then soft scoring (prefer/avoid).

    Gate evaluation:
      - constraints.must rules: ALL must pass (each failure → gate fail)
      - gates.hard_filters: evaluated per hard_filters_mode
          "require_all" → each failing filter is a gate failure (AND: all must pass)
          "require_any" → gate fails only if ALL filters fail (OR: at least one must pass)
      - gates.reject_anomalies: any matching anomaly → gate fail
      - gates.required_evidence_fields: missing field → gate fail

    Soft scoring (only when gates pass):
      - base = 5.0
      - prefer rules → +weight or weighted sum  (None/neutral fields contribute 0)
      - avoid rules → -severity (None/neutral fields contribute 0)
      - signal boosts: evidence_present, salary_disclosed (configurable field path)
      - penalties: incomplete, inference_used, prompt_injection_suspected,
                   missing_salary, old_posting, excess_hybrid_days
    """

    def __init__(self, config: SoftScoringConfig):
        """Initialise scorer with a SoftScoringConfig."""
        self.config = config

    def score(self, record: BaseResult, constraints: BaseConstraints) -> ScoredResult:
        gate_passed, gate_failures = self._apply_gates(record, constraints)
        score, breakdown = (
            self._apply_soft_scoring(record, constraints) if gate_passed else (None, None)
        )
        return ScoredResult(
            **record.model_dump(),
            gate_passed=gate_passed,
            gate_failures=gate_failures,
            score=score,
            score_breakdown=breakdown,
        )

    def _apply_gates(
        self, record: BaseResult, constraints: BaseConstraints
    ) -> tuple[bool, list[str]]:
        """Evaluate all hard gates; return (passed, list_of_failure_reasons).

        Checks, in order: must rules → hard_filters → anomaly rejections → required evidence.
        A non-empty failure list means the gate did not pass.
        """
        failures: list[str] = []
        failures.extend(self._evaluate_must_failures(record, constraints))
        failures.extend(self._evaluate_hard_filter_failures(record))
        failures.extend(self._evaluate_anomaly_failures(record))
        failures.extend(self._evaluate_required_evidence_failures(record))
        return len(failures) == 0, failures

    def _evaluate_must_failures(
        self, record: BaseResult, constraints: BaseConstraints
    ) -> list[str]:
        failures: list[str] = []
        for rule in constraints.must:
            if self._check_rule(record, rule) is False:
                failures.append(f"constraint.must: {rule.reason or rule.field}")
        return failures

    def _evaluate_hard_filter_failures(self, record: BaseResult) -> list[str]:
        hard_filters = self.config.gates.hard_filters
        if not hard_filters:
            return []
        hf_results = [self._check_rule(record, hf) for hf in hard_filters]
        hf_fails = [r is False for r in hf_results]
        if self.config.gates.hard_filters_mode == "require_any":
            return ["hard_filters: all failed"] if all(hf_fails) else []
        failures: list[str] = []
        for hf, failed in zip(hard_filters, hf_fails, strict=True):
            if failed:
                failures.append(f"hard_filter: {hf.reason or hf.field}")
        return failures

    def _evaluate_anomaly_failures(self, record: BaseResult) -> list[str]:
        return [
            f"anomaly: {anomaly}"
            for anomaly in record.anomalies
            if anomaly in self.config.gates.reject_anomalies
        ]

    def _evaluate_required_evidence_failures(self, record: BaseResult) -> list[str]:
        failures: list[str] = []
        evidence_fields = {e.field for e in record.evidence}
        for required in self.config.gates.required_evidence_fields:
            if not any(self._field_path_matches(required, ef) for ef in evidence_fields):
                failures.append(f"missing_evidence: {required}")
        return failures

    def _apply_soft_scoring(
        self, record: BaseResult, constraints: BaseConstraints
    ) -> tuple[float, ScoringBreakdown]:
        """Compute soft score (base + boosts - penalties), clamped to [0, 10].

        Only called when all gates pass. Returns (final_score, breakdown).
        """
        base = 5.0
        data = record.model_dump()
        boosts = self._compute_prefer_boosts(record, constraints, data)
        avoid_penalty = self._compute_avoid_penalty(record, constraints)
        penalties = self._compute_generic_penalties(record)
        signal_boosts, signal_penalties = self._compute_signal_adjustments(record, data)
        boosts += signal_boosts
        penalties += signal_penalties

        raw = base + boosts - avoid_penalty - penalties
        final = max(0.0, min(10.0, raw))
        return final, ScoringBreakdown(
            base=base,
            boosts=boosts,
            avoid_penalty=avoid_penalty,
            penalties=penalties,
            raw_score=raw,
            final_score=final,
        )

    def _compute_prefer_boosts(
        self, record: BaseResult, constraints: BaseConstraints, data: dict[str, Any]
    ) -> float:
        boosts = 0.0
        for rule in constraints.prefer:
            if self._check_rule(record, rule) is True:
                boosts += self._compute_rule_boost(data, rule)
        return boosts

    def _compute_avoid_penalty(self, record: BaseResult, constraints: BaseConstraints) -> float:
        avoid_penalty = 0.0
        for rule in constraints.avoid:
            if self._check_rule(record, rule) is True:
                avoid_penalty += rule.severity or self.config.avoid_penalty_default
        return avoid_penalty

    def _compute_generic_penalties(self, record: BaseResult) -> float:
        penalties = 0.0
        if record.incomplete:
            penalties += self.config.penalties.incomplete
        if record.inferences:
            penalties += self.config.penalties.inference_used
        if _PROMPT_INJECTION_ANOMALY in record.anomalies:
            penalties += self.config.penalties.prompt_injection_suspected
        return penalties

    def _compute_signal_adjustments(
        self, record: BaseResult, data: dict[str, Any]
    ) -> tuple[float, float]:
        boosts = 0.0
        penalties = 0.0

        salary_val = self._get_nested(data, self.config.signal_boost.salary_field)
        if salary_val not in (None, _MISSING):
            boosts += self.config.signal_boost.salary_disclosed
        else:
            penalties += self.config.penalties.missing_salary

        if record.evidence:
            boosts += self.config.signal_boost.evidence_present

        penalties += self._numeric_threshold_penalty(
            data=data,
            field_path=self.config.penalties.old_posting.field,
            threshold=self.config.penalties.old_posting.threshold,
            penalty=self.config.penalties.old_posting.penalty,
        )
        penalties += self._numeric_threshold_penalty(
            data=data,
            field_path=self.config.penalties.excess_hybrid_days.field,
            threshold=self.config.penalties.excess_hybrid_days.threshold,
            penalty=self.config.penalties.excess_hybrid_days.penalty,
        )

        return boosts, penalties

    def _numeric_threshold_penalty(
        self,
        *,
        data: dict[str, Any],
        field_path: str,
        threshold: int,
        penalty: float,
    ) -> float:
        value = self._get_nested(data, field_path)
        if value in (None, _MISSING):
            return 0.0
        if not self._is_numeric(value):
            logger.warning(
                "Type mismatch for penalty field '%s': expected numeric, got %s",
                field_path,
                type(value).__name__,
            )
            return 0.0
        return penalty if value > threshold else 0.0

    def _check_rule(self, record: BaseResult, rule: ConstraintRule) -> bool | None:
        """Evaluate a single rule against a record.

        Returns:
            True  — rule satisfied
            False — rule not satisfied (field present but condition unmet, or absent/null + neutral_if_na=False)
            None  — neutral (field absent + neutral_if_na=True; contributes 0 to scoring)

        Gate callers treat None as pass (no failure).
        Scoring callers only act on True.

        Distinction between absent vs explicit null:
            _MISSING (key not in dict): neutral_if_na applies → None or False
            None     (explicit null):   neutral_if_na applies → None or False
        """
        value = self._get_nested(record.model_dump(), rule.field)
        if value in (_MISSING, None):
            return None if rule.neutral_if_na else False
        op = rule.op
        if op in {"=", "in", "contains_any", "contains_all", "weighted"}:
            return self._evaluate_non_numeric_operator(value, rule)
        if op in {">=", "<=", "<", ">"}:
            return self._safe_compare(value, rule.value, op, rule.field)
        logger.warning("Unknown operator: %s", op)
        return False

    @staticmethod
    def _evaluate_non_numeric_operator(value: Any, rule: ConstraintRule) -> bool:
        if rule.op == "=":
            return value == rule.value
        if rule.op == "in":
            return value in rule.value
        if not isinstance(value, list):
            return False
        if rule.op in {"contains_any", "weighted"}:
            return any(v in rule.value for v in value)
        return all(v in value for v in rule.value)

    @staticmethod
    def _compute_rule_boost(data: dict, rule: ConstraintRule) -> float:
        """Compute the boost for a prefer rule that evaluated True.

        For 'weighted' op: sum weights[i] for each value[i] present in the field.
        For all other ops: return rule.weight.
        """
        if rule.op != "weighted":
            return rule.weight or 1.0
        value = HeuristicScorer._get_nested(data, rule.field)
        if not isinstance(value, list) or not rule.weights:
            return rule.weight or 1.0
        if len(rule.weights) != len(rule.value):
            logger.warning(f"weighted op: weights length mismatch for field '{rule.field}'")
            return rule.weight or 1.0
        return sum(w for v, w in zip(rule.value, rule.weights, strict=True) if v in value)

    @staticmethod
    def _get_nested(data: dict, path: str) -> Any:
        """Resolve a dotted field path against a nested dict (e.g. 'economics.salary_eur_gross').

        Returns:
            _MISSING   — key absent at any level (field does not exist in the record)
            None       — key present but value is explicitly null
            value      — the field value
        """
        cur: Any = data
        for part in path.split("."):
            if not isinstance(cur, dict):
                return _MISSING
            cur = cur.get(part, _MISSING)
            if cur is _MISSING:
                return _MISSING
        return cur

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @staticmethod
    def _field_path_matches(required: str, evidence_field: str) -> bool:
        if required == evidence_field:
            return True
        return required.startswith(f"{evidence_field}.") or evidence_field.startswith(
            f"{required}."
        )

    def _safe_compare(
        self,
        value: Any,
        target: Any,
        op: str,
        field: str,
    ) -> bool:
        try:
            if op == ">=":
                return value >= target
            if op == "<=":
                return value <= target
            if op == "<":
                return value < target
            if op == ">":
                return value > target
            return False
        except TypeError:
            logger.warning(
                "Type mismatch for rule field '%s' with op '%s': %s vs %s",
                field,
                op,
                type(value).__name__,
                type(target).__name__,
            )
            return False


class MockScorer(ScoringPort):
    """Mock scorer returning fixed scores (for testing)."""

    def __init__(self, return_value: float = 5.0, return_gate_passed: bool = True):
        """Configure fixed return values; calls are recorded in self.calls."""
        self.return_value = return_value
        self.return_gate_passed = return_gate_passed
        self.calls: list = []

    def score(self, record: BaseResult, constraints: BaseConstraints) -> ScoredResult:
        self.calls.append((record, constraints))
        score = self.return_value if self.return_gate_passed else None
        breakdown = (
            ScoringBreakdown(
                base=5.0,
                boosts=0.0,
                avoid_penalty=0.0,
                penalties=0.0,
                raw_score=self.return_value,
                final_score=self.return_value,
            )
            if self.return_gate_passed
            else None
        )
        return ScoredResult(
            **record.model_dump(),
            gate_passed=self.return_gate_passed,
            gate_failures=[] if self.return_gate_passed else ["mock: gate failed"],
            score=score,
            score_breakdown=breakdown,
        )
