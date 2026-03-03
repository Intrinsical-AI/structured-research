"""Integration tests for AtomsGrounding with real atoms files.

These tests load actual YAML files from config/job_search/profile_1/atoms/ and verify
that the grounding adapter resolves contexts, claims, and evidence correctly.
They require the repository's config directory to be present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from structured_search.infra.grounding import AtomsGrounding

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def grounding(atoms_dir: Path) -> AtomsGrounding:
    """AtomsGrounding loaded from the real job_search atoms directory."""
    if not atoms_dir.is_dir():
        pytest.skip(f"Atoms directory not found: {atoms_dir}")
    return AtomsGrounding(atoms_dir=atoms_dir)


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------


class TestContextLoading:
    def test_contexts_are_loaded(self, grounding: AtomsGrounding):
        """At least one context atom must be present."""
        contexts = grounding.get_context(domain="job_search")
        assert len(contexts) > 0, "No contexts loaded for domain 'job_search'"

    def test_all_contexts_have_required_fields(self, grounding: AtomsGrounding):
        for ctx in grounding.get_context(domain="job_search"):
            assert ctx.id, f"Context missing id: {ctx}"
            assert ctx.domain == "job_search"
            assert ctx.content, f"Context '{ctx.id}' has empty content"

    def test_unknown_domain_returns_empty(self, grounding: AtomsGrounding):
        assert grounding.get_context(domain="__nonexistent__") == []


# ---------------------------------------------------------------------------
# Claims loading
# ---------------------------------------------------------------------------


class TestClaimsLoading:
    def test_claims_are_loaded(self, grounding: AtomsGrounding):
        """At least one claim must be loaded from subdirectories."""
        assert len(grounding.claims) > 0, (
            "No claims loaded — check that rglob traverses subdirectories"
        )

    def test_claims_reference_existing_contexts(self, grounding: AtomsGrounding):
        context_ids = {ctx.id for ctx in grounding.contexts}
        for claim in grounding.claims:
            assert claim.parent_context_id in context_ids, (
                f"Claim '{claim.id}' references unknown context '{claim.parent_context_id}'"
            )

    def test_get_claims_by_context_returns_subset(self, grounding: AtomsGrounding):
        contexts = grounding.get_context(domain="job_search")
        assert contexts, "No contexts to test with"
        ctx = contexts[0]
        claims = grounding.get_claims_by_context(ctx.id)
        # All returned claims must belong to this context
        for claim in claims:
            assert claim.parent_context_id == ctx.id

    def test_get_claims_for_unknown_context(self, grounding: AtomsGrounding):
        assert grounding.get_claims_by_context("__nonexistent__") == []


# ---------------------------------------------------------------------------
# Evidence loading
# ---------------------------------------------------------------------------


class TestEvidenceLoading:
    def test_evidence_is_loaded(self, grounding: AtomsGrounding):
        """At least one evidence atom must be loaded from subdirectories."""
        assert len(grounding.evidence) > 0, (
            "No evidence loaded — check that rglob traverses subdirectories"
        )

    def test_get_evidence_returns_correct_atom(self, grounding: AtomsGrounding):
        evid_id = next(iter(grounding.evidence))
        atom = grounding.get_evidence(evid_id)
        assert atom is not None
        assert atom.id == evid_id

    def test_get_evidence_missing_returns_none(self, grounding: AtomsGrounding):
        assert grounding.get_evidence("__nonexistent__") is None

    def test_evidence_atoms_have_urls(self, grounding: AtomsGrounding):
        for atom in grounding.evidence.values():
            assert atom.url, f"Evidence '{atom.id}' has no URL"


# ---------------------------------------------------------------------------
# Referential integrity
# ---------------------------------------------------------------------------


class TestReferentialIntegrity:
    def test_claim_evidence_ids_resolve(self, grounding: AtomsGrounding):
        """Every evidence_id referenced by a claim must exist in the evidence index."""
        missing: list[str] = []
        for claim in grounding.claims:
            for eid in claim.evidence_ids:
                if grounding.get_evidence(eid) is None:
                    missing.append(f"{claim.id} → {eid}")
        assert not missing, "Dangling evidence references:\n" + "\n".join(missing)
