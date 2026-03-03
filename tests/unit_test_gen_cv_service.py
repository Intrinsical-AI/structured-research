"""Unit tests for GenCVService claim allow-list behavior."""

from __future__ import annotations

from structured_search.domain.atoms import ClaimAtom, ContextAtom, EvidenceAtom
from structured_search.infra.llm import MockLLM
from structured_search.ports.grounding import GroundingPort
from structured_search.tasks.gen_cv.models import CandidateAtomsProfile, JobDescription
from structured_search.tasks.gen_cv.service import GenCVService


class _FakeGrounding(GroundingPort):
    def __init__(self) -> None:
        self._contexts = [
            ContextAtom(
                id="ctx-1",
                domain="job_search",
                content="Search/retrieval project context",
                tags=["python", "rag"],
            )
        ]
        self._claims = [
            ClaimAtom(
                id="claim-1",
                parent_context_id="ctx-1",
                claim="Implemented RAG bootstrapping pipeline.",
                evidence_ids=["ev-1"],
            ),
            ClaimAtom(
                id="claim-2",
                parent_context_id="ctx-1",
                claim="Evaluated retrieval quality with BEIR-like setup.",
                evidence_ids=["ev-2"],
            ),
        ]
        self._evidence = {
            "ev-1": EvidenceAtom(id="ev-1", claim_id="claim-1", url="https://example.com/1"),
            "ev-2": EvidenceAtom(id="ev-2", claim_id="claim-2", url="https://example.com/2"),
        }

    def get_context(self, domain: str) -> list[ContextAtom]:
        return [ctx for ctx in self._contexts if ctx.domain == domain]

    def get_claims_by_context(self, context_id: str) -> list[ClaimAtom]:
        return [claim for claim in self._claims if claim.parent_context_id == context_id]

    def get_evidence(self, evidence_id: str) -> EvidenceAtom | None:
        return self._evidence.get(evidence_id)


def _job() -> JobDescription:
    return JobDescription(
        id="job-1",
        title="Senior Search Engineer",
        company="Acme",
        stack=["Python", "RAG"],
    )


def _candidate() -> CandidateAtomsProfile:
    return CandidateAtomsProfile(id="cand-1", seniority="senior")


class _FakePromptComposer:
    def load_base(self, sections=None) -> str:
        return "IDENTITY FROM PORT"

    def compose(self, task, step, profile=None, include_base=True) -> str:
        return f"{task}:{step}:{profile}:{include_base}"


class _EmptyGrounding(GroundingPort):
    def get_context(self, domain: str) -> list[ContextAtom]:
        _ = domain
        return []

    def get_claims_by_context(self, context_id: str) -> list[ClaimAtom]:
        _ = context_id
        return []

    def get_evidence(self, evidence_id: str) -> EvidenceAtom | None:
        _ = evidence_id
        return None


def test_generate_enforces_allowed_claim_ids_in_prompt_and_output():
    llm = MockLLM(
        json_response={
            "summary": "Tailored CV summary.",
            "highlights": ["A", "B"],
            "cited_claim_ids": ["claim-1", "claim-2", "claim-999"],
        }
    )
    service = GenCVService(llm=llm, grounding=_FakeGrounding())

    result = service.generate(
        job=_job(),
        candidate=_candidate(),
        allowed_claim_ids=["claim-2"],
    )

    assert result.grounded_claim_ids == ["claim-2"]
    assert len(llm.extract_json_calls) == 1
    prompt = llm.extract_json_calls[0][0]
    assert "[claim-2]" in prompt
    assert "[claim-1]" not in prompt
    assert "You may cite ONLY the following claim IDs: claim-2" in prompt


def test_generate_uses_injected_prompt_composer_port():
    llm = MockLLM(
        json_response={
            "summary": "Tailored CV summary.",
            "highlights": [],
            "cited_claim_ids": ["claim-1"],
        }
    )
    service = GenCVService(
        llm=llm,
        grounding=_FakeGrounding(),
        prompt_composer=_FakePromptComposer(),
    )
    service.generate(job=_job(), candidate=_candidate())

    prompt = llm.extract_json_calls[0][0]
    assert "IDENTITY FROM PORT" in prompt


def test_generate_prompt_allows_job_and_candidate_when_grounding_is_empty():
    llm = MockLLM(
        json_response={
            "summary": "CV from job and candidate data.",
            "highlights": ["A"],
            "cited_claim_ids": [],
        }
    )
    service = GenCVService(llm=llm, grounding=_EmptyGrounding())
    service.generate(job=_job(), candidate=_candidate())

    prompt = llm.extract_json_calls[0][0]
    assert "Grounded facts are unavailable for this profile." in prompt
    assert "Use ONLY data from the 'Target Job' and 'Candidate' sections below." in prompt
    assert "No data provided" in prompt
    assert "## Target Job" in prompt
    assert "## Candidate" in prompt


def test_render_prompt_returns_base_and_rendered_prompt_artifacts():
    service = GenCVService(
        llm=MockLLM(),
        grounding=_FakeGrounding(),
        prompt_composer=_FakePromptComposer(),
    )

    artifacts = service.render_prompt(job=_job(), candidate=_candidate())

    assert artifacts.base_prompt == "IDENTITY FROM PORT"
    assert "IDENTITY FROM PORT" in artifacts.rendered_prompt
    assert "## Grounded Facts (cite IDs of facts you use)" in artifacts.rendered_prompt
    assert "[claim-1]" in artifacts.rendered_prompt
