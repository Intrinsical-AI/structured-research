"""Unit tests for HeuristicScorer: gates, soft scoring, neutral_if_na, operators."""

import logging
from datetime import datetime

import pytest

from structured_search.domain import (
    BaseConstraints,
    BaseResult,
    ConstraintRule,
    EvidenceAnchor,
    EvidenceLocator,
    InferenceRecord,
)
from structured_search.infra.scoring import HeuristicScorer
from structured_search.infra.scoring_config import (
    GatesConfig,
    PenaltiesConfig,
    SignalBoostConfig,
    SoftScoringConfig,
)


def _make_config(**kwargs) -> SoftScoringConfig:
    return SoftScoringConfig(**kwargs)


def _make_record(**kwargs) -> BaseResult:
    defaults = {"id": "r1", "source": "test"}
    defaults.update(kwargs)
    return BaseResult(**defaults)


def _make_constraints(must=None, prefer=None, avoid=None) -> BaseConstraints:
    return BaseConstraints(
        domain="test",
        must=must or [],
        prefer=prefer or [],
        avoid=avoid or [],
    )


def _rule(field, op, value, **kwargs) -> ConstraintRule:
    return ConstraintRule(field=field, op=op, value=value, **kwargs)


def _scorer(gates=None, signal_boost=None, penalties=None) -> HeuristicScorer:
    config = SoftScoringConfig(
        gates=gates or GatesConfig(),
        signal_boost=signal_boost or SignalBoostConfig(),
        penalties=penalties or PenaltiesConfig(),
    )
    return HeuristicScorer(config)


# ============================================================================
# TestCheckRule — operadores y neutral_if_na
# ============================================================================


class TestCheckRule:
    def _scorer(self):
        return _scorer()

    def test_eq_operator_match(self):
        scorer = self._scorer()
        record = _make_record(modality="remote")
        rule = _rule("modality", "=", "remote")
        assert scorer._check_rule(record, rule) is True

    def test_eq_operator_no_match(self):
        scorer = self._scorer()
        record = _make_record(modality="on_site")
        rule = _rule("modality", "=", "remote")
        assert scorer._check_rule(record, rule) is False

    def test_in_operator_match(self):
        scorer = self._scorer()
        record = _make_record(modality="hybrid")
        rule = _rule("modality", "in", ["remote", "hybrid"])
        assert scorer._check_rule(record, rule) is True

    def test_in_operator_no_match(self):
        scorer = self._scorer()
        record = _make_record(modality="on_site")
        rule = _rule("modality", "in", ["remote", "hybrid"])
        assert scorer._check_rule(record, rule) is False

    def test_contains_any_match(self):
        scorer = self._scorer()
        record = _make_record(stack=["Python", "Go"])
        rule = _rule("stack", "contains_any", ["Go", "Rust"])
        assert scorer._check_rule(record, rule) is True

    def test_contains_any_no_match(self):
        scorer = self._scorer()
        record = _make_record(stack=["Java", "Scala"])
        rule = _rule("stack", "contains_any", ["Go", "Rust"])
        assert scorer._check_rule(record, rule) is False

    def test_contains_all_match(self):
        scorer = self._scorer()
        record = _make_record(stack=["Python", "Go", "Rust"])
        rule = _rule("stack", "contains_all", ["Python", "Go"])
        assert scorer._check_rule(record, rule) is True

    def test_contains_all_no_match(self):
        scorer = self._scorer()
        record = _make_record(stack=["Python"])
        rule = _rule("stack", "contains_all", ["Python", "Go"])
        assert scorer._check_rule(record, rule) is False

    def test_gte_match(self):
        scorer = self._scorer()
        record = _make_record(score=8.0)
        rule = _rule("score", ">=", 5.0)
        assert scorer._check_rule(record, rule) is True

    def test_gt_no_match(self):
        scorer = self._scorer()
        record = _make_record(score=5.0)
        rule = _rule("score", ">", 5.0)
        assert scorer._check_rule(record, rule) is False

    def test_lte_match(self):
        scorer = self._scorer()
        record = _make_record(age=25)
        rule = _rule("age", "<=", 30)
        assert scorer._check_rule(record, rule) is True

    def test_lt_no_match(self):
        scorer = self._scorer()
        record = _make_record(age=30)
        rule = _rule("age", "<", 30)
        assert scorer._check_rule(record, rule) is False

    def test_compare_type_mismatch_returns_false_instead_of_raising(self):
        scorer = self._scorer()
        record = _make_record(posted_at=datetime.now())
        rule = _rule("posted_at", ">=", 10)
        assert scorer._check_rule(record, rule) is False

    def test_nested_field_match(self):
        scorer = self._scorer()
        record = BaseResult(id="r1", source="test", seniority={"level": "senior"})
        rule = _rule("seniority.level", "=", "senior")
        assert scorer._check_rule(record, rule) is True

    def test_nested_field_deep_miss(self):
        scorer = self._scorer()
        record = _make_record()  # no seniority field
        rule = _rule("seniority.level", "=", "senior")
        # field absent + neutral_if_na=False → False
        assert scorer._check_rule(record, rule) is False

    def test_unknown_operator_rejected_at_validation(self):
        """op is now a Literal — invalid operators are caught at model creation."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            _rule("x", "~=", 1)


# ============================================================================
# TestNeutralIfNa — semántica correcta del three-state return
# ============================================================================


class TestNeutralIfNa:
    def test_absent_field_neutral_if_na_true_returns_none(self):
        scorer = _scorer()
        record = _make_record()  # no 'salary' field
        rule = _rule("salary", ">=", 80000, neutral_if_na=True)
        assert scorer._check_rule(record, rule) is None

    def test_absent_field_neutral_if_na_false_returns_false(self):
        scorer = _scorer()
        record = _make_record()
        rule = _rule("salary", ">=", 80000, neutral_if_na=False)
        assert scorer._check_rule(record, rule) is False

    def test_null_field_neutral_if_na_true_returns_none(self):
        scorer = _scorer()
        record = _make_record(salary=None)
        rule = _rule("salary", ">=", 80000, neutral_if_na=True)
        assert scorer._check_rule(record, rule) is None

    def test_null_field_neutral_if_na_false_returns_false(self):
        scorer = _scorer()
        record = _make_record(salary=None)
        rule = _rule("salary", ">=", 80000, neutral_if_na=False)
        assert scorer._check_rule(record, rule) is False

    def test_prefer_neutral_field_adds_no_boost(self):
        """neutral_if_na=True on a prefer rule must NOT add boost when field is absent."""
        prefer_rule = _rule("salary", ">=", 80000, weight=3.0, neutral_if_na=True)
        constraints = _make_constraints(prefer=[prefer_rule])
        record = _make_record()  # no salary field
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is True
        # base=5.0, no boost, no signal_boost defaults → score should be 5.0
        assert scored.score_breakdown.boosts == 0.0

    def test_prefer_neutral_field_adds_boost_when_present(self):
        prefer_rule = _rule("salary", ">=", 80000, weight=3.0, neutral_if_na=True)
        constraints = _make_constraints(prefer=[prefer_rule])
        record = _make_record(salary=90000)
        scored = _scorer().score(record, constraints)
        assert scored.score_breakdown.boosts == 3.0

    def test_avoid_neutral_field_adds_no_penalty(self):
        """neutral_if_na=True on an avoid rule must NOT add penalty when field is absent."""
        avoid_rule = _rule("age_days", ">", 30, severity=2.0, neutral_if_na=True)
        constraints = _make_constraints(avoid=[avoid_rule])
        record = _make_record()  # no age_days field
        scored = _scorer().score(record, constraints)
        assert scored.score_breakdown.avoid_penalty == 0.0

    def test_must_neutral_field_passes_gate(self):
        """neutral_if_na=True on a must rule should NOT fail the gate when field is absent."""
        must_rule = _rule("modality", "=", "remote", neutral_if_na=True)
        constraints = _make_constraints(must=[must_rule])
        record = _make_record()  # no modality field
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is True
        assert scored.gate_failures == []

    def test_must_absent_field_without_neutral_fails_gate(self):
        must_rule = _rule("modality", "=", "remote", neutral_if_na=False)
        constraints = _make_constraints(must=[must_rule])
        record = _make_record()
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is False
        assert len(scored.gate_failures) == 1

    def test_must_null_field_with_neutral_if_na_true_passes_gate(self):
        must_rule = _rule("visa_sponsorship_offered", "=", True, neutral_if_na=True)
        constraints = _make_constraints(must=[must_rule])
        record = _make_record(visa_sponsorship_offered=None)
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is True
        assert scored.gate_failures == []


# ============================================================================
# TestHeuristicScorerGates
# ============================================================================


class TestHeuristicScorerGates:
    def test_must_rule_pass(self):
        rule = _rule("modality", "in", ["remote", "hybrid"])
        constraints = _make_constraints(must=[rule])
        record = _make_record(modality="remote")
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is True
        assert scored.gate_failures == []

    def test_must_rule_fail(self):
        rule = _rule("modality", "in", ["remote", "hybrid"], reason="only remote/hybrid")
        constraints = _make_constraints(must=[rule])
        record = _make_record(modality="on_site")
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is False
        assert "constraint.must: only remote/hybrid" in scored.gate_failures

    def test_must_rule_fail_uses_field_as_reason_when_no_reason(self):
        rule = _rule("modality", "=", "remote")
        constraints = _make_constraints(must=[rule])
        record = _make_record(modality="hybrid")
        scored = _scorer().score(record, constraints)
        assert "constraint.must: modality" in scored.gate_failures

    def test_multiple_must_rules_all_reported(self):
        rules = [
            _rule("modality", "=", "remote", reason="remote-only"),
            _rule("seniority", "=", "senior", reason="senior-only"),
        ]
        constraints = _make_constraints(must=rules)
        record = _make_record(modality="hybrid", seniority="mid")
        scored = _scorer().score(record, constraints)
        assert scored.gate_passed is False
        assert len(scored.gate_failures) == 2

    def test_reject_anomaly(self):
        gates = GatesConfig(reject_anomalies=["prompt_injection_suspected"])
        scorer = _scorer(gates=gates)
        record = BaseResult(id="r1", source="test", anomalies=["prompt_injection_suspected"])
        constraints = _make_constraints()
        scored = scorer.score(record, constraints)
        assert scored.gate_passed is False
        assert any("anomaly:" in f for f in scored.gate_failures)

    def test_non_rejected_anomaly_passes(self):
        gates = GatesConfig(reject_anomalies=["prompt_injection_suspected"])
        scorer = _scorer(gates=gates)
        record = BaseResult(id="r1", source="test", anomalies=["missing_field"])
        constraints = _make_constraints()
        scored = scorer.score(record, constraints)
        assert scored.gate_passed is True

    def test_required_evidence_field_present(self):
        gates = GatesConfig(required_evidence_fields=["title"])
        scorer = _scorer(gates=gates)
        anchor = EvidenceAnchor(
            id="e1",
            field="title",
            quote="Engineer",
            url="https://example.com",
            retrieved_at=datetime.now(),
            locator=EvidenceLocator(type="css_selector", value=".title"),
        )
        record = BaseResult(id="r1", source="test", evidence=[anchor])
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is True

    def test_required_evidence_field_absent(self):
        gates = GatesConfig(required_evidence_fields=["title"])
        scorer = _scorer(gates=gates)
        record = _make_record()  # no evidence
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is False
        assert "missing_evidence: title" in scored.gate_failures

    def test_required_evidence_parent_matches_evidence_child(self):
        gates = GatesConfig(required_evidence_fields=["apply_url"])
        scorer = _scorer(gates=gates)
        anchor = EvidenceAnchor(
            id="e1",
            field="apply_url.href",
            quote="Apply here",
            url="https://example.com",
            retrieved_at=datetime.now(),
            locator=EvidenceLocator(type="css_selector", value=".apply"),
        )
        record = BaseResult(id="r1", source="test", evidence=[anchor])
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is True

    def test_required_evidence_child_matches_evidence_parent(self):
        gates = GatesConfig(required_evidence_fields=["apply_url.href"])
        scorer = _scorer(gates=gates)
        anchor = EvidenceAnchor(
            id="e1",
            field="apply_url",
            quote="Apply here",
            url="https://example.com",
            retrieved_at=datetime.now(),
            locator=EvidenceLocator(type="css_selector", value=".apply"),
        )
        record = BaseResult(id="r1", source="test", evidence=[anchor])
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is True

    def test_hard_filter_any_mode_each_failure_reported(self):
        """mode='require_all': each failing hard filter is its own gate failure (AND)."""
        hf = _rule("modality", "=", "remote", reason="remote-filter")
        gates = GatesConfig(hard_filters=[hf], hard_filters_mode="require_all")
        scorer = _scorer(gates=gates)
        record = _make_record(modality="hybrid")
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is False
        assert "hard_filter: remote-filter" in scored.gate_failures

    def test_hard_filter_any_mode_passes_when_matched(self):
        hf = _rule("modality", "=", "remote")
        gates = GatesConfig(hard_filters=[hf], hard_filters_mode="require_all")
        scorer = _scorer(gates=gates)
        record = _make_record(modality="remote")
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is True

    def test_hard_filter_all_mode_fails_only_when_all_fail(self):
        """mode='require_any': gate fails only if ALL hard filters fail (OR)."""
        hf1 = _rule("modality", "=", "remote")
        hf2 = _rule("seniority", "=", "senior")
        gates = GatesConfig(hard_filters=[hf1, hf2], hard_filters_mode="require_any")
        scorer = _scorer(gates=gates)
        # Both fail → gate fails
        record = _make_record(modality="hybrid", seniority="mid")
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is False
        assert "hard_filters: all failed" in scored.gate_failures

    def test_hard_filter_all_mode_passes_when_one_passes(self):
        """mode='require_any': gate passes if at least one hard filter passes (OR)."""
        hf1 = _rule("modality", "=", "remote")
        hf2 = _rule("seniority", "=", "senior")
        gates = GatesConfig(hard_filters=[hf1, hf2], hard_filters_mode="require_any")
        scorer = _scorer(gates=gates)
        # Only hf1 fails, hf2 passes → gate passes
        record = _make_record(modality="hybrid", seniority="senior")
        scored = scorer.score(record, _make_constraints())
        assert scored.gate_passed is True

    def test_gate_fail_produces_no_score(self):
        must_rule = _rule("modality", "=", "remote")
        constraints = _make_constraints(must=[must_rule])
        record = _make_record(modality="on_site")
        scored = _scorer().score(record, constraints)
        assert scored.score is None
        assert scored.score_breakdown is None


# ============================================================================
# TestHeuristicScorerSoftScoring
# ============================================================================


class TestHeuristicScorerSoftScoring:
    def test_base_score_no_rules(self):
        scored = _scorer().score(_make_record(), _make_constraints())
        assert scored.gate_passed is True
        assert scored.score_breakdown.base == 5.0
        # with all defaults at 0.0, boosts=0, penalties=0 (except missing_salary default 0)
        assert scored.score_breakdown.boosts == 0.0

    def test_prefer_rule_adds_boost(self):
        prefer = [_rule("modality", "=", "remote", weight=2.0)]
        constraints = _make_constraints(prefer=prefer)
        record = _make_record(modality="remote")
        scored = _scorer().score(record, constraints)
        assert scored.score_breakdown.boosts == 2.0
        assert scored.score == 7.0  # base 5.0 + 2.0

    def test_multiple_prefer_rules_accumulate(self):
        prefer = [
            _rule("modality", "=", "remote", weight=2.0),
            _rule("level", "=", "senior", weight=1.5),
        ]
        constraints = _make_constraints(prefer=prefer)
        record = _make_record(modality="remote", level="senior")
        scored = _scorer().score(record, constraints)
        assert scored.score_breakdown.boosts == 3.5

    def test_avoid_rule_adds_penalty(self):
        avoid = [_rule("age_days", ">", 30, severity=1.5)]
        constraints = _make_constraints(avoid=avoid)
        record = _make_record(age_days=45)
        scored = _scorer().score(record, constraints)
        assert scored.score_breakdown.avoid_penalty == 1.5

    def test_score_clamped_at_zero(self):
        avoid = [_rule("modality", "=", "on_site", severity=20.0)]
        constraints = _make_constraints(avoid=avoid)
        record = _make_record(modality="on_site")
        scored = _scorer().score(record, constraints)
        assert scored.score == 0.0
        assert scored.score_breakdown.raw_score < 0.0

    def test_score_clamped_at_ten(self):
        prefer = [_rule("modality", "=", "remote", weight=20.0)]
        constraints = _make_constraints(prefer=prefer)
        record = _make_record(modality="remote")
        scored = _scorer().score(record, constraints)
        assert scored.score == 10.0
        assert scored.score_breakdown.raw_score > 10.0

    def test_incomplete_record_penalty(self):
        penalties = PenaltiesConfig(incomplete=2.0)
        record = BaseResult(id="r1", source="test", incomplete=True)
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 2.0

    def test_inference_used_penalty(self):
        penalties = PenaltiesConfig(inference_used=1.0)
        inference = InferenceRecord(
            field="salary",
            value=80000,
            reason="estimated",
            confidence=0.6,
            evidence_ids=[],
        )
        record = BaseResult(id="r1", source="test", inferences=[inference])
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 1.0

    def test_prompt_injection_penalty_only_for_specific_anomaly(self):
        penalties = PenaltiesConfig(prompt_injection_suspected=3.0)
        # generic anomaly → no prompt injection penalty
        record_generic = BaseResult(id="r1", source="test", anomalies=["missing_field"])
        scored_generic = _scorer(penalties=penalties).score(record_generic, _make_constraints())
        assert "prompt_injection_suspected" not in record_generic.anomalies
        assert scored_generic.score_breakdown.penalties == 0.0

        # prompt injection anomaly → penalty applied
        record_pi = BaseResult(id="r2", source="test", anomalies=["prompt_injection_suspected"])
        scored_pi = _scorer(penalties=penalties).score(record_pi, _make_constraints())
        assert scored_pi.score_breakdown.penalties == 3.0

    def test_evidence_present_boost(self):
        signal_boost = SignalBoostConfig(evidence_present=1.0)
        anchor = EvidenceAnchor(
            id="e1",
            field="title",
            quote="Eng",
            url="https://example.com",
            retrieved_at=datetime.now(),
            locator=EvidenceLocator(type="css_selector", value=".t"),
        )
        record = BaseResult(id="r1", source="test", evidence=[anchor])
        scored = _scorer(signal_boost=signal_boost).score(record, _make_constraints())
        assert scored.score_breakdown.boosts == 1.0

    def test_salary_disclosed_boost_and_missing_salary_penalty(self):
        signal_boost = SignalBoostConfig(
            salary_disclosed=1.5, salary_field="economics.salary_eur_gross"
        )
        penalties = PenaltiesConfig(missing_salary=0.5)

        # salary present → boost
        record_with_salary = BaseResult(
            id="r1", source="test", economics={"salary_eur_gross": 85000}
        )
        scored_with = _scorer(signal_boost=signal_boost, penalties=penalties).score(
            record_with_salary, _make_constraints()
        )
        assert scored_with.score_breakdown.boosts == 1.5
        assert scored_with.score_breakdown.penalties == 0.0

        # salary absent → penalty
        record_no_salary = _make_record()
        scored_without = _scorer(signal_boost=signal_boost, penalties=penalties).score(
            record_no_salary, _make_constraints()
        )
        assert scored_without.score_breakdown.boosts == 0.0
        assert scored_without.score_breakdown.penalties == 0.5

    def test_old_posting_penalty(self):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            old_posting=ThresholdPenalty(penalty=1.0, field="recency.activity_age_days", threshold=30),
        )
        record = BaseResult(id="r1", source="test", recency={"activity_age_days": 45})
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 1.0

    def test_old_posting_penalty_ignores_type_mismatch(self):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            old_posting=ThresholdPenalty(penalty=1.0, field="recency.activity_age_days", threshold=30),
        )
        record = BaseResult(id="r1", source="test", recency={"activity_age_days": "old"})
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 0.0

    def test_old_posting_not_applied_when_recent(self):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            old_posting=ThresholdPenalty(penalty=1.0, field="recency.activity_age_days", threshold=30),
        )
        record = BaseResult(id="r1", source="test", recency={"activity_age_days": 10})
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 0.0

    def test_old_posting_numeric_below_threshold_does_not_log_type_mismatch(self, caplog):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            old_posting=ThresholdPenalty(penalty=1.0, field="recency.activity_age_days", threshold=30),
        )
        record = BaseResult(id="r1", source="test", recency={"activity_age_days": 10})
        with caplog.at_level(logging.WARNING):
            _scorer(penalties=penalties).score(record, _make_constraints())
        assert "Type mismatch for penalty field 'recency.activity_age_days'" not in caplog.text

    def test_excess_hybrid_days_penalty(self):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            excess_hybrid_days=ThresholdPenalty(penalty=2.0, field="onsite_days_per_week", threshold=3),
        )
        record = BaseResult(id="r1", source="test", onsite_days_per_week=4)
        scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 2.0

    def test_excess_hybrid_numeric_below_threshold_does_not_log_type_mismatch(self, caplog):
        from structured_search.infra.scoring_config import ThresholdPenalty

        penalties = PenaltiesConfig(
            excess_hybrid_days=ThresholdPenalty(penalty=2.0, field="onsite_days_per_week", threshold=3),
        )
        record = BaseResult(id="r1", source="test", onsite_days_per_week=2.5)
        with caplog.at_level(logging.WARNING):
            scored = _scorer(penalties=penalties).score(record, _make_constraints())
        assert scored.score_breakdown.penalties == 0.0
        assert "Type mismatch for penalty field 'onsite_days_per_week'" not in caplog.text

    def test_score_breakdown_consistency(self):
        """raw_score = base + boosts - avoid_penalty - penalties."""
        prefer = [_rule("x", "=", 1, weight=2.0)]
        avoid = [_rule("y", "=", 1, severity=1.0)]
        constraints = _make_constraints(prefer=prefer, avoid=avoid)
        record = _make_record(x=1, y=1)
        scored = _scorer().score(record, constraints)
        bd = scored.score_breakdown
        expected_raw = bd.base + bd.boosts - bd.avoid_penalty - bd.penalties
        assert abs(bd.raw_score - expected_raw) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
