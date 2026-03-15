#!/usr/bin/env python3
"""Render vulnerability JSONL into canonical docs and optionally import them into rag-prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

SYNERGY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SYNERGY_ROOT.parent
DEFAULT_CHUNK_SIZE = 5000
MAX_CONTENT_CHARS = 1800
MAX_CODE_EXCERPT_CHARS = 500


def _load_structured_search():
    import sys

    structured_research_src = WORKSPACE_ROOT / "structured-research" / "src"
    if str(structured_research_src) not in sys.path:
        sys.path.insert(0, str(structured_research_src))

    from structured_search.application.core.ingest_service import ingest_validate_jsonl
    from structured_search.application.core.task_registry import get_task_registry
    from structured_search.domain.vuln_triage.models import VulnRecord

    return {
        "VulnRecord": VulnRecord,
        "get_task_registry": get_task_registry,
        "ingest_validate_jsonl": ingest_validate_jsonl,
    }


def load_vuln_records(
    input_path: Path,
    *,
    allow_invalid: bool = False,
) -> list[Any]:
    sr = _load_structured_search()
    plugin = sr["get_task_registry"]().get("vuln_triage")
    raw_text = input_path.read_text(encoding="utf-8")
    ingest = sr["ingest_validate_jsonl"](raw_text=raw_text, record_model=plugin.record_model)
    if ingest.invalid and not allow_invalid:
        first = ingest.invalid[0]
        raise ValueError(
            f"Input contains {len(ingest.invalid)} invalid records; first error: "
            f"line={first.line_no} kind={first.kind} msg={first.message}"
        )
    vuln_model = sr["VulnRecord"]
    return [vuln_model.model_validate(record) for record in ingest.valid]


def derive_dataset_name(input_path: Path) -> str:
    return input_path.stem.replace(" ", "-").replace("_", "-")


def derive_snapshot_id(input_path: Path, dataset_name: str) -> str:
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()[:12]
    return f"{dataset_name}-{digest}"


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def render_vuln_content(record: Any) -> str:
    title = f"{record.cve_id or record.osv_id or record.id} [{record.cwe_id or 'no-cwe'}]"
    lines = [
        title,
        f"summary: {record.summary or 'n/a'}",
        f"language: {record.language or 'unknown'}",
        f"repo: {record.repo or 'unknown'}",
        f"severity: {record.severity or 'unknown'}",
    ]
    if record.cvss_score is not None:
        lines.append(f"cvss_score: {record.cvss_score}")
    if record.file_path:
        lines.append(f"file_path: {record.file_path}")
    if record.vuln_code:
        excerpt = _truncate_text(record.vuln_code, MAX_CODE_EXCERPT_CHARS)
        lines.append(f"vuln_code_excerpt: {excerpt}")

    content = "\n".join(lines)
    return _truncate_text(content, MAX_CONTENT_CHARS)


def build_doc_metadata(record: Any) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    metadata = {
        "record_type": "vuln_record",
        "id": payload.get("id"),
        "osv_id": payload.get("osv_id"),
        "cve_id": payload.get("cve_id"),
        "cwe_id": payload.get("cwe_id"),
        "repo": payload.get("repo"),
        "repo_url": payload.get("repo_url"),
        "language": payload.get("language"),
        "file_path": payload.get("file_path"),
        "commit_vuln": payload.get("commit_vuln"),
        "commit_fix": payload.get("commit_fix"),
        "commit_vuln_url": payload.get("commit_vuln_url"),
        "commit_fix_url": payload.get("commit_fix_url"),
        "severity": payload.get("severity"),
        "cvss_score": payload.get("cvss_score"),
        "has_code_pair": payload.get("has_code_pair"),
        "trainable": payload.get("trainable"),
        "published_at": payload.get("published_at"),
        "updated_at": payload.get("updated_at"),
        "source": payload.get("source"),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def build_canonical_payloads(
    records: list[Any],
    *,
    dataset_name: str,
    scope: str,
    snapshot_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    canonical_source = next(
        (
            str(record.source).strip()
            for record in records
            if getattr(record, "source", None) and str(record.source).strip()
        ),
        dataset_name,
    )
    source_id = f"vuln-source:{canonical_source}"
    documents = [
        {
            "external_id": f"vuln:{record.id}",
            "content": render_vuln_content(record),
            "source_id": source_id,
            "metadata": build_doc_metadata(record),
        }
        for record in records
    ]

    payloads: list[dict[str, Any]] = []
    for index in range(0, len(documents), chunk_size):
        chunk = documents[index : index + chunk_size]
        payloads.append(
            {
                "scope": scope,
                "snapshot_id": snapshot_id,
                "replace_scope": index == 0,
                "documents": chunk,
            }
        )
    return payloads or [
        {
            "scope": scope,
            "snapshot_id": snapshot_id,
            "replace_scope": True,
            "documents": [],
        }
    ]


def write_payloads(payloads: list[dict[str, Any]], output_path: Path) -> list[Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(payloads) == 1:
        output_path.write_text(
            json.dumps(payloads[0], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return [output_path]

    written_paths: list[Path] = []
    for idx, payload in enumerate(payloads, start=1):
        path = output_path.with_name(f"{output_path.stem}-{idx:04d}{output_path.suffix}")
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written_paths.append(path)
    return written_paths


def import_payloads(payload_paths: list[Path], rag_repo: Path) -> None:
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", str(WORKSPACE_ROOT / ".uv_cache"))
    for path in payload_paths:
        cmd = ["uv", "run", "rag-import-canonical", "--json", str(path)]
        completed = subprocess.run(cmd, cwd=rag_repo, env=env, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"rag-import-canonical failed for payload {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render vulnerability JSONL into rag-prototype canonical docs."
    )
    parser.add_argument("--input", required=True, help="Path to FCE-style vulnerability JSONL.")
    parser.add_argument(
        "--payload-out",
        required=True,
        help="Path where the canonical payload JSON is written.",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Logical dataset name. Defaults to the input filename stem.",
    )
    parser.add_argument(
        "--snapshot-id",
        default=None,
        help="Snapshot id. Defaults to a deterministic hash of the input file.",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="Canonical scope. Defaults to vuln-triage:{dataset_name}.",
    )
    parser.add_argument(
        "--rag-repo",
        default=str(WORKSPACE_ROOT / "rag-prototype"),
        help="Path to the rag-prototype repository.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Maximum number of documents per canonical import payload.",
    )
    parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Continue with valid records even if some JSONL lines are invalid.",
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
        help="Only write payload JSON; do not call rag-import-canonical.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    payload_out = Path(args.payload_out)
    dataset_name = args.dataset_name or derive_dataset_name(input_path)
    snapshot_id = args.snapshot_id or derive_snapshot_id(input_path, dataset_name)
    scope = args.scope or f"vuln-triage:{dataset_name}"

    try:
        records = load_vuln_records(input_path, allow_invalid=args.allow_invalid)
        payloads = build_canonical_payloads(
            records,
            dataset_name=dataset_name,
            scope=scope,
            snapshot_id=snapshot_id,
            chunk_size=args.chunk_size,
        )
        payload_paths = write_payloads(payloads, payload_out)
        if not args.no_import:
            import_payloads(payload_paths, Path(args.rag_repo))
    except Exception as exc:
        parser.exit(1, f"{exc}\n")

    summary = {
        "dataset_name": dataset_name,
        "scope": scope,
        "snapshot_id": snapshot_id,
        "payloads_written": [str(path) for path in payload_paths],
        "documents": sum(len(payload["documents"]) for payload in payloads),
        "imported": not args.no_import,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
