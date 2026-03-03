#!/usr/bin/env python3
"""Validate atoms dataset integrity.

Checks:
- schema compliance for ContextAtom, ClaimAtom, and EvidenceAtom;
- unique IDs;
- claim parent/evidence referential integrity;
- verification_level requirements (0..3);
- placeholder/public evidence safety rules;
- canonical facet tags with alias normalization support.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML object")
    return data


def load_schema_validators(schemas_dir: Path) -> dict[str, Draft202012Validator]:
    schema_files = {
        "context": "context_atom.schema.yaml",
        "claim": "claim_atom.schema.yaml",
        "evidence": "evidence_atom.schema.yaml",
    }
    return {t: Draft202012Validator(load_yaml(schemas_dir / f)) for t, f in schema_files.items()}


def load_canon_tags(path: Path) -> dict[str, dict[str, Any]]:
    data = load_yaml(path)
    facets = data.get("facets")
    if not isinstance(facets, dict):
        raise ValueError(f"{path}: 'facets' must be a mapping")
    result: dict[str, dict[str, Any]] = {}
    for name, fd in facets.items():
        if not isinstance(fd, dict):
            continue
        canonical: set[str] = {str(v) for v in fd.get("canonical", []) if isinstance(v, str)}
        aliases_raw = fd.get("aliases", {})
        aliases: dict[str, str] = (
            {
                str(k): str(v)
                for k, v in aliases_raw.items()
                if isinstance(k, str) and isinstance(v, str)
            }
            if isinstance(aliases_raw, dict)
            else {}
        )
        result[str(name)] = {"canonical": canonical, "aliases": aliases}
    return result


def validate_facet_tags(
    claim: dict[str, Any], claim_path: Path, canon_tags: dict[str, dict[str, Any]]
) -> tuple[list, list]:
    errors: list = []
    warnings: list = []
    facets = claim.get("facets")
    if not isinstance(facets, dict):
        return errors, warnings
    for facet_name, facet_value in facets.items():
        if facet_name not in canon_tags or not isinstance(facet_value, list):
            continue
        canonical: set[str] = canon_tags[facet_name]["canonical"]
        aliases: dict[str, str] = canon_tags[facet_name]["aliases"]
        for raw_tag in facet_value:
            tag = str(raw_tag)
            normalized = aliases.get(tag, tag)
            if normalized not in canonical:
                errors.append(f"{claim_path}: facets.{facet_name} has unknown tag '{tag}'")
            elif normalized != tag:
                warnings.append(f"{claim_path}: alias '{tag}' → use canonical '{normalized}'")
    return errors, warnings


def discover_atom_files(atoms_dir: Path) -> list[Path]:
    """Discover all atom YAML files."""
    files: list[Path] = []
    for subdir in ("context", "claims", "evidence"):
        path = atoms_dir / subdir
        if not path.exists():
            continue
        files.extend(sorted(path.rglob("*.yaml")))
        files.extend(sorted(path.rglob("*.yml")))
    return sorted(set(files))


def schema_validate_atom(
    atom: dict[str, Any],
    path: Path,
    validators: dict[str, Draft202012Validator],
) -> tuple[str | None, list[str]]:
    """Validate atom against schema."""
    atom_type = atom.get("type")
    if not isinstance(atom_type, str):
        return None, [f"{path}: missing or invalid 'type'"]

    validator = validators.get(atom_type)
    if validator is None:
        return atom_type, [f"{path}: unsupported atom type '{atom_type}'"]

    errors = [
        f"{path}: schema error at {'/'.join(map(str, err.absolute_path)) or '<root>'}: {err.message}"
        for err in sorted(
            validator.iter_errors(atom),
            key=lambda e: (list(e.absolute_path), e.message),
        )
    ]
    return atom_type, errors


class ValidationReport:
    def __init__(self) -> None:
        self.contexts = 0
        self.claims = 0
        self.evidence = 0
        self.files_scanned = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self) -> bool:
        return len(self.errors) == 0


def _register_atom_id(
    *,
    atom_file: Path,
    atom: dict[str, Any],
    seen_ids: set[str],
    report: ValidationReport,
) -> str | None:
    atom_id = atom.get("id")
    if not isinstance(atom_id, str):
        return None
    if atom_id in seen_ids:
        report.errors.append(f"{atom_file}: duplicate atom id '{atom_id}'")
    seen_ids.add(atom_id)
    return atom_id


def _process_context_atom(
    *,
    atom_id: str | None,
    context_ids: set[str],
    report: ValidationReport,
) -> None:
    report.contexts += 1
    if atom_id is not None:
        context_ids.add(atom_id)


def _evidence_url_parts(url: Any) -> tuple[str, str]:
    if not isinstance(url, str):
        return "", ""
    parsed = urlparse(url)
    return parsed.netloc.lower(), parsed.scheme.lower()


def _process_evidence_atom(
    *,
    atom_file: Path,
    atom: dict[str, Any],
    atom_id: str | None,
    evidence_ids: set[str],
    evidence_by_id: dict[str, dict[str, Any]],
    report: ValidationReport,
) -> None:
    report.evidence += 1
    if atom_id is not None:
        evidence_ids.add(atom_id)
        evidence_by_id[atom_id] = atom

    visibility = atom.get("visibility")
    is_placeholder = bool(atom.get("is_placeholder", False))
    host, scheme = _evidence_url_parts(atom.get("url"))

    if is_placeholder and visibility != "private":
        report.errors.append(f"{atom_file}: is_placeholder=true requires visibility=private")
    if visibility == "public" and host in {"example.com", "www.example.com"}:
        report.errors.append(
            f"{atom_file}: public evidence cannot use placeholder domain example.com"
        )
    if visibility == "public" and scheme == "urn":
        report.errors.append(f"{atom_file}: public evidence cannot use URN URL")
    if visibility == "public" and atom.get("published_at") is None:
        report.warnings.append(
            f"{atom_file}: public evidence should include published_at when available"
        )


def _process_claim_atom(
    *,
    atom_file: Path,
    atom: dict[str, Any],
    canon_tags: dict[str, dict[str, Any]],
    claims_for_ref_checks: list[tuple[Path, dict[str, Any]]],
    report: ValidationReport,
) -> None:
    report.claims += 1
    claims_for_ref_checks.append((atom_file, atom))
    facet_errors, facet_warnings = validate_facet_tags(atom, atom_file, canon_tags)
    report.errors.extend(facet_errors)
    report.warnings.extend(facet_warnings)


def _claim_evidence_ids(claim: dict[str, Any]) -> list[str]:
    defensibility = claim.get("defensibility")
    if not isinstance(defensibility, dict):
        return []
    evidence_refs = defensibility.get("evidence_ids")
    if not isinstance(evidence_refs, list):
        return []
    return [str(item) for item in evidence_refs]


def _append_claim_parent_context_error(
    *,
    claim_path: Path,
    claim: dict[str, Any],
    context_ids: set[str],
    report: ValidationReport,
) -> None:
    parent_context_id = claim.get("parent_context_id")
    if isinstance(parent_context_id, str) and parent_context_id not in context_ids:
        report.errors.append(
            f"{claim_path}: parent_context_id '{parent_context_id}' does not exist"
        )


def _resolve_claim_evidence(
    *,
    claim_path: Path,
    evidence_list: list[str],
    evidence_ids: set[str],
    evidence_by_id: dict[str, dict[str, Any]],
    report: ValidationReport,
) -> list[dict[str, Any]]:
    referenced_evidence: list[dict[str, Any]] = []
    for evidence_id in evidence_list:
        if evidence_id not in evidence_ids:
            report.errors.append(f"{claim_path}: evidence_id '{evidence_id}' does not exist")
            continue
        referenced = evidence_by_id.get(evidence_id)
        if isinstance(referenced, dict):
            referenced_evidence.append(referenced)
    return referenced_evidence


def _append_claim_verification_errors(
    *,
    claim_path: Path,
    claim: dict[str, Any],
    referenced_evidence: list[dict[str, Any]],
    evidence_list: list[str],
    report: ValidationReport,
) -> None:
    defensibility = claim.get("defensibility")
    if not isinstance(defensibility, dict):
        return
    verification_level = defensibility.get("verification_level")

    if isinstance(verification_level, int) and verification_level >= 1 and not evidence_list:
        report.errors.append(
            f"{claim_path}: verification_level {verification_level} requires at least one evidence_id"
        )

    if isinstance(verification_level, int) and verification_level >= 2:
        for evidence in referenced_evidence:
            metadata = evidence.get("metadata")
            if not isinstance(metadata, dict):
                report.errors.append(
                    f"{claim_path}: verification_level {verification_level} requires evidence metadata"
                )
                continue
            quote = metadata.get("quote")
            locator = metadata.get("locator")
            if not isinstance(quote, str) or not quote.strip():
                report.errors.append(
                    f"{claim_path}: verification_level {verification_level} requires evidence quote"
                )
            if (
                not isinstance(locator, dict)
                or not locator.get("type")
                or not locator.get("value")
            ):
                report.errors.append(
                    f"{claim_path}: verification_level {verification_level} requires evidence locator"
                )

    if isinstance(verification_level, int) and verification_level >= 3:
        reproducibility_refs = defensibility.get("reproducibility_refs")
        if not isinstance(reproducibility_refs, list) or len(reproducibility_refs) == 0:
            report.errors.append(
                f"{claim_path}: verification_level {verification_level} requires defensibility.reproducibility_refs"
            )


def validate_bundle(atoms_dir: Path, schemas_dir: Path, canon_tags_file: Path) -> ValidationReport:
    report = ValidationReport()
    validators = load_schema_validators(schemas_dir)
    canon_tags = load_canon_tags(canon_tags_file)

    context_ids: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_by_id: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    claims_for_ref_checks: list[tuple[Path, dict[str, Any]]] = []

    for atom_file in discover_atom_files(atoms_dir):
        report.files_scanned += 1
        try:
            atom = load_yaml(atom_file)
        except Exception as exc:
            report.errors.append(f"{atom_file}: failed to parse YAML ({exc})")
            continue

        atom_type, schema_errors = schema_validate_atom(atom, atom_file, validators)
        report.errors.extend(schema_errors)
        if atom_type is None:
            continue

        atom_id = _register_atom_id(
            atom_file=atom_file,
            atom=atom,
            seen_ids=seen_ids,
            report=report,
        )

        if atom_type == "context":
            _process_context_atom(atom_id=atom_id, context_ids=context_ids, report=report)
            continue
        if atom_type == "evidence":
            _process_evidence_atom(
                atom_file=atom_file,
                atom=atom,
                atom_id=atom_id,
                evidence_ids=evidence_ids,
                evidence_by_id=evidence_by_id,
                report=report,
            )
            continue
        if atom_type == "claim":
            _process_claim_atom(
                atom_file=atom_file,
                atom=atom,
                canon_tags=canon_tags,
                claims_for_ref_checks=claims_for_ref_checks,
                report=report,
            )

    for claim_path, claim in claims_for_ref_checks:
        _append_claim_parent_context_error(
            claim_path=claim_path,
            claim=claim,
            context_ids=context_ids,
            report=report,
        )
        evidence_list = _claim_evidence_ids(claim)
        referenced_evidence = _resolve_claim_evidence(
            claim_path=claim_path,
            evidence_list=evidence_list,
            evidence_ids=evidence_ids,
            evidence_by_id=evidence_by_id,
            report=report,
        )
        _append_claim_verification_errors(
            claim_path=claim_path,
            claim=claim,
            referenced_evidence=referenced_evidence,
            evidence_list=evidence_list,
            report=report,
        )

    return report


def format_report(report: ValidationReport) -> str:
    lines: list[str] = []
    lines.append(
        "atoms validation summary: "
        f"files={report.files_scanned}, contexts={report.contexts}, claims={report.claims}, evidence={report.evidence}"
    )
    if report.errors:
        lines.append("errors:")
        lines.extend(f"  - {item}" for item in report.errors)
    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"  - {item}" for item in report.warnings)
    if report.ok():
        lines.append("status: OK")
    else:
        lines.append("status: FAILED")
    return "\n".join(lines)


def parse_args(argv) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Validate atoms dataset integrity")
    parser.add_argument(
        "--atoms-dir",
        default="config/job_search/profile_example/atoms",
        help="Atoms root directory",
    )
    parser.add_argument(
        "--schemas-dir",
        default="config/job_search/profile_example/atoms/schemas",
        help="Directory with atom schemas in YAML format",
    )
    parser.add_argument(
        "--canon-tags",
        default="config/job_search/profile_example/atoms/canon_tags.yaml",
        help="Canonical tags file",
    )
    return parser.parse_args(list(argv))


def main(argv=None) -> int:
    """Run atoms validation."""
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO)

    report = validate_bundle(
        atoms_dir=Path(args.atoms_dir),
        schemas_dir=Path(args.schemas_dir),
        canon_tags_file=Path(args.canon_tags),
    )
    print(format_report(report))
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
