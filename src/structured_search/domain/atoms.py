"""Domain atoms: context, claims, evidence.

Atoms are the foundation for grounding LLM outputs. They provide:
- Context: Background knowledge for a domain
- Claims: Factual assertions about a domain
- Evidence: Source material supporting claims

These models are used for validation, serialization, and LLM grounding.
Validation also uses JSON Schema for referential integrity checks.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================================
# Context Atom
# ============================================================================


class ContextAtom(BaseModel):
    """Background context for a domain.

    Provides foundational knowledge that claims refer to.
    Example: For job_search, contexts might be role definitions, tech stacks, etc.
    """

    id: str = Field(..., description="Unique context ID (e.g., 'ctx_001')")
    domain: str = Field(..., description="Domain this context belongs to (e.g., 'job_search')")
    content: str = Field(..., description="The context text")
    tags: list[str] = Field(default_factory=list, description="Semantic tags")
    created_at: datetime = Field(default_factory=datetime.now)
    source_url: str | None = Field(None, description="Where this context comes from")


# ============================================================================
# Claim Atom
# ============================================================================


class ClaimAtom(BaseModel):
    """A factual claim about a domain.

    Claims are grounded in context and backed by evidence.
    Example: "Python is essential for backend roles" (grounded in job market context)
    """

    id: str = Field(..., description="Unique claim ID (e.g., 'claim_001')")
    parent_context_id: str = Field(
        ..., description="Reference to ContextAtom this claim belongs to"
    )
    claim: str = Field(..., description="The claim statement")
    facets: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Semantic facets with tags (e.g., 'languages': ['Python', 'Go'])",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="References to EvidenceAtom supporting this claim",
    )
    verification_level: int = Field(
        0,
        ge=0,
        le=3,
        description="Confidence level: 0=unverified, 1=low, 2=medium, 3=high",
    )
    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Evidence Atom
# ============================================================================


class EvidenceAtom(BaseModel):
    """Evidence supporting a claim.

    Atomic unit of evidence linking claims to source material.
    Example: A quote from a job posting supporting a claim about salary ranges.
    """

    id: str = Field(..., description="Unique evidence ID (e.g., 'evid_001')")
    claim_id: str | None = Field(None, description="Reference to ClaimAtom this supports")
    quote: str | None = Field(None, description="Direct quote from source")
    url: str = Field(..., description="Source URL")
    retrieved_at: datetime | None = Field(None, description="When was this evidence retrieved")
    source_kind: str = Field("other", description="Source type: html, pdf, api, or other")
    locator: str | None = Field(None, description="Location in source (CSS selector, XPath, etc.)")
    public_safe: bool = Field(
        True,
        description="Safe to share publicly (no personal data, no placeholder URLs)",
    )
    created_at: datetime = Field(default_factory=datetime.now)
