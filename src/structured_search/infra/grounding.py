"""Grounding adapters: AtomsGrounding."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from structured_search.domain import ClaimAtom, ContextAtom, EvidenceAtom
from structured_search.ports.grounding import GroundingPort

logger = logging.getLogger(__name__)


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML object")
    return data


def _yaml_to_claim(data: dict) -> dict:
    """Map the rich YAML claim schema to ClaimAtom fields.

    The YAML stores the claim text under ``variants.technical`` and
    evidence metadata under ``defensibility``.
    """
    defensibility = data.get("defensibility") or {}
    variants = data.get("variants") or {}
    return {
        "id": data["id"],
        "parent_context_id": data["parent_context_id"],
        "claim": variants.get("technical") or variants.get("short") or "",
        "evidence_ids": defensibility.get("evidence_ids") or [],
        "verification_level": defensibility.get("verification_level", 0),
    }


def _yaml_to_evidence(data: dict) -> dict:
    """Map the rich YAML evidence schema to EvidenceAtom fields.

    The YAML stores ``quote`` and ``retrieved_at`` under ``metadata``
    and uses ``kind`` instead of ``source_kind``.
    """
    metadata = data.get("metadata") or {}
    return {
        "id": data["id"],
        "url": data["url"],
        "quote": metadata.get("quote"),
        "retrieved_at": metadata.get("retrieved_at"),
        "source_kind": data.get("kind", "other"),
    }


class AtomsGrounding(GroundingPort):
    """Load atoms from YAML files and serve them as grounding context.

    Directory layout expected:
      <atoms_dir>/context/**/*.yaml
      <atoms_dir>/claims/**/*.yaml
      <atoms_dir>/evidence/**/*.yaml

    All three directories are searched recursively to support subdirectory
    organisation by project or source.
    """

    def __init__(self, atoms_dir: Path | str):
        self.atoms_dir = Path(atoms_dir)
        self._load()

    def _load(self) -> None:
        self.contexts: list[ContextAtom] = []
        self.claims: list[ClaimAtom] = []
        self.evidence: dict[str, EvidenceAtom] = {}

        for yaml_file in (
            (self.atoms_dir / "context").rglob("*.yaml")
            if (self.atoms_dir / "context").exists()
            else []
        ):
            try:
                self.contexts.append(ContextAtom.model_validate(_load_yaml(yaml_file)))
            except Exception as e:
                logger.warning(f"Skipping {yaml_file}: {e}")

        for yaml_file in (
            (self.atoms_dir / "claims").rglob("*.yaml")
            if (self.atoms_dir / "claims").exists()
            else []
        ):
            try:
                self.claims.append(ClaimAtom.model_validate(_yaml_to_claim(_load_yaml(yaml_file))))
            except Exception as e:
                logger.warning(f"Skipping {yaml_file}: {e}")

        for yaml_file in (
            (self.atoms_dir / "evidence").rglob("*.yaml")
            if (self.atoms_dir / "evidence").exists()
            else []
        ):
            try:
                atom = EvidenceAtom.model_validate(_yaml_to_evidence(_load_yaml(yaml_file)))
                self.evidence[atom.id] = atom
            except Exception as e:
                logger.warning(f"Skipping {yaml_file}: {e}")

        logger.info(
            f"Atoms loaded: {len(self.contexts)} contexts, "
            f"{len(self.claims)} claims, {len(self.evidence)} evidence"
        )

    def get_context(self, domain: str) -> list[ContextAtom]:
        return [c for c in self.contexts if c.domain == domain]

    def get_claims_by_context(self, context_id: str) -> list[ClaimAtom]:
        return [c for c in self.claims if c.parent_context_id == context_id]

    def get_evidence(self, evidence_id: str) -> EvidenceAtom | None:
        return self.evidence.get(evidence_id)
