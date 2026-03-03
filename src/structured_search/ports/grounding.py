"""GroundingPort: interface for atoms-based grounding."""

from abc import ABC, abstractmethod

from structured_search.domain import ClaimAtom, ContextAtom, EvidenceAtom


class GroundingPort(ABC):
    """Port for accessing atoms (context, claims, evidence).

    Used to ground LLM outputs in domain knowledge.
    Provides access to curated facts, claims, and supporting evidence.
    """

    @abstractmethod
    def get_context(self, domain: str) -> list[ContextAtom]:
        """Get all context atoms for a domain.

        Args:
            domain: Domain name (e.g., 'job_search')

        Returns:
            List of context atoms
        """
        pass

    @abstractmethod
    def get_claims_by_context(self, context_id: str) -> list[ClaimAtom]:
        """Get claims for a specific context.

        Args:
            context_id: ID of the parent context

        Returns:
            List of claim atoms
        """
        pass

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> EvidenceAtom | None:
        """Get specific evidence atom.

        Args:
            evidence_id: ID of the evidence

        Returns:
            Evidence atom, or None if not found
        """
        pass
