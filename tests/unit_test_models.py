"""Unit tests for domain models and task-specific models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from structured_search.domain import (
    BaseConstraints,
    BaseResult,
    ConstraintRule,
    EvidenceAnchor,
    EvidenceLocator,
    ScoredResult,
)
from structured_search.domain.atoms import ClaimAtom, ContextAtom, EvidenceAtom
from structured_search.domain.gen_cv.models import (
    CandidateAtomsProfile,
    ExperienceEntry,
    GeneratedCV,
    JobDescription,
    SkillSet,
)
from structured_search.domain.job_search.models import JobPosting


class TestBaseResult:
    def test_create_base_result(self):
        result = BaseResult(id="test_001", source="test_source")
        assert result.id == "test_001"
        assert result.extracted_at is not None

    def test_base_result_with_evidence(self):
        anchor = EvidenceAnchor(
            id="evid_001",
            field="title",
            quote="Software Engineer",
            url="https://example.com",
            retrieved_at=datetime.now(),
            locator=EvidenceLocator(type="css_selector", value=".job-title"),
        )
        result = BaseResult(id="test_001", source="test_source", evidence=[anchor])
        assert result.evidence[0].field == "title"


class TestScoredResult:
    def test_create_scored_result(self):
        from structured_search.domain import ScoringBreakdown

        result = ScoredResult(
            id="test_001",
            source="test_source",
            gate_passed=True,
            score=7.0,
            score_breakdown=ScoringBreakdown(
                base=5.0,
                boosts=2.0,
                avoid_penalty=0.0,
                penalties=0.0,
                raw_score=7.0,
                final_score=7.0,
            ),
        )
        assert result.score == 7.0
        assert result.score_breakdown.final_score == 7.0


class TestAtoms:
    def test_context_atom(self):
        ctx = ContextAtom(id="ctx_001", domain="job_search", content="Python is essential")
        assert ctx.domain == "job_search"

    def test_claim_atom(self):
        claim = ClaimAtom(
            id="claim_001",
            parent_context_id="ctx_001",
            claim="Python required",
            evidence_ids=["evid_001"],
            verification_level=2,
        )
        assert claim.verification_level == 2

    def test_evidence_atom(self):
        evid = EvidenceAtom(
            id="evid_001",
            claim_id="claim_001",
            quote="5+ years Python",
            url="https://example.com",
            retrieved_at=datetime.now(),
            source_kind="html",
        )
        assert evid.source_kind == "html"


class TestJobPosting:
    def test_create_job_posting(self):
        from structured_search.domain.job_search.models import GeoInfo, SeniorityInfo

        posting = JobPosting(
            id="job_001",
            source="linkedin",
            company="Acme",
            title="Senior Engineer",
            posted_at=datetime.now(),
            apply_url="https://example.com",
            geo=GeoInfo(region="Europe", city="Berlin"),
            modality="hybrid",
            seniority=SeniorityInfo(level="senior"),
        )
        assert posting.modality == "hybrid"


class TestGenCVModels:
    def test_job_description(self):
        job = JobDescription(
            id="job_001",
            title="Senior Infra Engineer",
            company="CloudCo",
            stack=["Go", "K8s"],
        )
        assert "Go" in job.stack

    def test_candidate_atoms_profile(self):
        candidate = CandidateAtomsProfile(
            id="cand_001",
            seniority="senior",
            tech_stack=SkillSet(languages=["Go", "Python"], platforms=["Kubernetes"]),
            experience=[
                ExperienceEntry(
                    company="TechCorp",
                    title="Senior SRE",
                    duration_months=36,
                    highlights=["Led K8s migration"],
                )
            ],
        )
        assert candidate.experience[0].duration_months == 36
        assert "Go" in candidate.tech_stack.languages

    def test_generated_cv(self):
        cv = GeneratedCV(
            id="job_001__cand_001",
            source="gen_cv",
            job_id="job_001",
            candidate_id="cand_001",
            summary="Experienced infra engineer.",
            highlights=["Led K8s migration"],
        )
        assert len(cv.highlights) == 1
        assert cv.extracted_at is not None  # generated_at → extracted_at (from BaseResult)

    def test_model_dump_roundtrip(self):
        candidate = CandidateAtomsProfile(id="cand_001", seniority="senior")
        data = candidate.model_dump()
        restored = CandidateAtomsProfile.model_validate(data)
        assert restored.id == candidate.id


class TestConstraints:
    def test_create_constraints(self):
        rule = ConstraintRule(field="seniority.level", op="=", value="senior", weight=2.0)
        constraints = BaseConstraints(domain="job_search", must=[rule])
        assert constraints.must[0].field == "seniority.level"

    def test_operator_in_requires_list_value(self):
        with pytest.raises(ValidationError):
            ConstraintRule(field="modality", op="in", value="remote")

    def test_operator_gte_requires_numeric_value(self):
        with pytest.raises(ValidationError):
            ConstraintRule(field="salary", op=">=", value="high")

    def test_weighted_requires_weights(self):
        with pytest.raises(ValidationError):
            ConstraintRule(field="domain.tags", op="weighted", value=["IR", "RAG"])

    def test_weights_for_non_weighted_op_rejected(self):
        with pytest.raises(ValidationError):
            ConstraintRule(
                field="seniority.level",
                op="=",
                value="senior",
                weights=[1.0],
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
