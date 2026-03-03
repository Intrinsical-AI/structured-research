"""CV generation service."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from structured_search.domain.atoms import ClaimAtom, ContextAtom
from structured_search.domain.gen_cv.models import (
    CandidateAtomsProfile,
    CVOutput,
    GeneratedCV,
    JobDescription,
)
from structured_search.ports.grounding import GroundingPort
from structured_search.ports.llm import LLMPort
from structured_search.ports.prompting import PromptComposerPort

logger = logging.getLogger(__name__)

_TOP_K_CONTEXTS = 4
_MAX_CLAIMS_PER_CONTEXT = 6


@dataclass(frozen=True)
class PromptArtifacts:
    """Rendered prompt plus the base identity prompt used to build it."""

    base_prompt: str
    rendered_prompt: str


class GenCVService:
    """Generate a tailored CV using LLM + grounded claims."""

    def __init__(
        self,
        llm: LLMPort,
        grounding: GroundingPort,
        domain: str = "job_search",
        prompt_composer: PromptComposerPort | None = None,
    ):
        self.llm = llm
        self.grounding = grounding
        self.domain = domain
        self.composer = prompt_composer

    def generate(
        self,
        job: JobDescription,
        candidate: CandidateAtomsProfile,
        allowed_claim_ids: list[str] | None = None,
    ) -> GeneratedCV:
        logger.info(f"Generating CV: job={job.id}, candidate={candidate.id}")
        allowed_claim_ids_set = set(allowed_claim_ids) if allowed_claim_ids is not None else None

        ranked, claims_by_ctx, all_claim_ids = self._select_grounded_claims(
            job,
            allowed_claim_ids_set,
        )
        prompt = self._build_prompt(
            job,
            candidate,
            ranked,
            claims_by_ctx,
            allowed_claim_ids_set,
        )
        output = CVOutput.model_validate(self.llm.extract_json(prompt, CVOutput))

        grounded = [cid for cid in output.cited_claim_ids if cid in all_claim_ids]

        return GeneratedCV(
            id=f"{job.id}__{candidate.id}",
            source=self.llm.__class__.__name__,
            job_id=job.id,
            candidate_id=candidate.id,
            title=f"{candidate.seniority.capitalize()} {job.title}",
            summary=output.summary,
            highlights=output.highlights,
            grounded_claim_ids=grounded,
            model_used=getattr(self.llm, "model", None),
            raw_output=None,
        )

    def render_prompt(
        self,
        job: JobDescription,
        candidate: CandidateAtomsProfile,
        allowed_claim_ids: list[str] | None = None,
    ) -> PromptArtifacts:
        allowed_claim_ids_set = set(allowed_claim_ids) if allowed_claim_ids is not None else None
        ranked, claims_by_ctx, _ = self._select_grounded_claims(job, allowed_claim_ids_set)
        base_prompt = self._resolve_identity_prompt()
        rendered_prompt = self._build_prompt(
            job=job,
            candidate=candidate,
            contexts=ranked,
            claims_by_ctx=claims_by_ctx,
            allowed_claim_ids=allowed_claim_ids_set,
            identity=base_prompt,
        )
        return PromptArtifacts(base_prompt=base_prompt, rendered_prompt=rendered_prompt)

    def _select_grounded_claims(
        self,
        job: JobDescription,
        allowed_claim_ids_set: set[str] | None,
    ) -> tuple[list[ContextAtom], dict[str, list[ClaimAtom]], set[str]]:
        contexts = self.grounding.get_context(domain=self.domain)
        ranked = self._rank_contexts(contexts, job)[:_TOP_K_CONTEXTS]

        claims_by_ctx: dict[str, list[ClaimAtom]] = {}
        for ctx in ranked:
            claims = self.grounding.get_claims_by_context(ctx.id)
            if allowed_claim_ids_set is not None:
                claims = [claim for claim in claims if claim.id in allowed_claim_ids_set]
            claims_by_ctx[ctx.id] = claims
        all_claim_ids = {claim.id for claims in claims_by_ctx.values() for claim in claims}
        return ranked, claims_by_ctx, all_claim_ids

    def _resolve_identity_prompt(self) -> str:
        if self.composer is not None:
            return self.composer.load_base(sections=["01_identity.md"])
        return "You are an expert CV writer. Generate a tailored CV section."

    @staticmethod
    def _rank_contexts(contexts: list[ContextAtom], job: JobDescription) -> list[ContextAtom]:
        job_terms = {t.lower() for t in job.stack}
        if not job_terms:
            return contexts

        def score(ctx: ContextAtom) -> int:
            tag_hits = len(job_terms & {t.lower() for t in ctx.tags})
            content_hits = sum(
                1
                for t in job_terms
                if re.search(rf"\b{re.escape(t)}\b", ctx.content, re.IGNORECASE)
            )
            return tag_hits + content_hits

        return sorted(contexts, key=score, reverse=True)

    def _build_prompt(
        self,
        job: JobDescription,
        candidate: CandidateAtomsProfile,
        contexts: list[ContextAtom],
        claims_by_ctx: dict[str, list[ClaimAtom]],
        allowed_claim_ids: set[str] | None = None,
        identity: str | None = None,
    ) -> str:
        resolved_identity = identity if identity is not None else self._resolve_identity_prompt()

        stack_str = ", ".join(job.stack) if job.stack else "not specified"
        lang_str = ", ".join(candidate.tech_stack.languages) or "not specified"
        spoken_lang_str = ", ".join(candidate.spoken_languages) or "not specified"
        experience_count = len(candidate.experience)
        education_count = len(candidate.education)
        job_modality = job.modality or "not specified"
        job_location = job.location or "not specified"
        job_description = job.description or "not provided"
        job_url = job.url or "not provided"
        candidate_name = candidate.name or "not provided"

        fact_lines: list[str] = []
        for ctx in contexts:
            claims = claims_by_ctx.get(ctx.id, [])[:_MAX_CLAIMS_PER_CONTEXT]
            if not claims:
                continue
            fact_lines.append(f"\n### {ctx.content[:80]}")
            for claim in claims:
                ev_url = self._resolve_evidence_url(claim)
                ev_str = f"\n    Evidence: {ev_url}" if ev_url else ""
                fact_lines.append(f"  [{claim.id}] {claim.claim}{ev_str}")

        has_grounded_facts = bool(fact_lines)
        facts_section = "\n".join(fact_lines) if has_grounded_facts else "  (none)"

        lines = [resolved_identity]
        if has_grounded_facts:
            lines.extend(
                [
                    "IMPORTANT: Only use the grounded facts provided below. Do not invent new facts.",
                    "Cite each fact you use by including its ID in cited_claim_ids.",
                ]
            )
        else:
            lines.extend(
                [
                    "Grounded facts are unavailable for this profile.",
                    "Use ONLY data from the 'Target Job' and 'Candidate' sections below.",
                    "Do not invent missing details. If data is missing, omit it instead of writing placeholders like 'No data provided' or 'N/A'.",
                    "When grounded facts are unavailable, return cited_claim_ids as an empty list.",
                ]
            )

        if allowed_claim_ids is not None and has_grounded_facts:
            allowed_str = ", ".join(sorted(allowed_claim_ids)) or "(none)"
            lines.append(f"You may cite ONLY the following claim IDs: {allowed_str}")
        lines.extend(
            [
                "",
                "## Target Job",
                f"Title: {job.title}",
                f"Company: {job.company}",
                f"Stack: {stack_str}",
                f"Seniority: {job.seniority or 'not specified'}",
                f"Modality: {job_modality}",
                f"Location: {job_location}",
                f"Description: {job_description}",
                f"URL: {job_url}",
                "",
                "## Candidate",
                f"Name: {candidate_name}",
                f"Seniority: {candidate.seniority}",
                f"Tech Languages: {lang_str}",
                f"Spoken Languages: {spoken_lang_str}",
                f"Location: {candidate.location or 'not specified'}",
                f"Timezone: {candidate.timezone or 'not specified'}",
                f"Availability Days: {candidate.availability_days}",
                f"Experience Entries: {experience_count}",
                f"Education Entries: {education_count}",
                "",
                "## Grounded Facts (cite IDs of facts you use)",
                facts_section,
                "",
                "Output JSON matching this schema exactly:",
                '{"summary": "...", "highlights": ["...", "..."], "cited_claim_ids": ["CLAIM-ID-1"]}',
            ]
        )
        return "\n".join(lines)

    def _resolve_evidence_url(self, claim: ClaimAtom) -> str | None:
        for eid in claim.evidence_ids:
            atom = self.grounding.get_evidence(eid)
            if atom is not None:
                return atom.url
        return None
