#!/usr/bin/env python3
"""Batch vulnerability triage over JSONL records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SYNERGY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SYNERGY_ROOT.parent


def _load_structured_search():
    import sys

    structured_research_src = WORKSPACE_ROOT / "structured-research" / "src"
    if str(structured_research_src) not in sys.path:
        sys.path.insert(0, str(structured_research_src))

    from structured_search.application.common.dependencies import ApplicationDependencies
    from structured_search.application.core.ingest_service import ingest_validate_jsonl
    from structured_search.application.core.run_service import run_score
    from structured_search.application.core.task_registry import get_task_registry
    from structured_search.contracts import RunScoreRequest
    from structured_search.infra.persistence_fs import (
        FilesystemProfileRepository,
        FilesystemRunRepository,
    )

    return {
        "ApplicationDependencies": ApplicationDependencies,
        "FilesystemProfileRepository": FilesystemProfileRepository,
        "FilesystemRunRepository": FilesystemRunRepository,
        "RunScoreRequest": RunScoreRequest,
        "get_task_registry": get_task_registry,
        "ingest_validate_jsonl": ingest_validate_jsonl,
        "run_score": run_score,
    }


def build_dependencies(structured_research_root: Path, runs_dir: Path):
    sr = _load_structured_search()
    return sr["ApplicationDependencies"](
        profile_repo=sr["FilesystemProfileRepository"](
            base_dir=structured_research_root / "config"
        ),
        run_repo=sr["FilesystemRunRepository"](base_dir=runs_dir),
        prompts_dir=structured_research_root / "resources" / "prompts",
    )


def load_valid_records(
    input_path: Path,
    *,
    task_id: str = "vuln_triage",
) -> tuple[list[dict[str, Any]], list[Any], Any]:
    sr = _load_structured_search()
    plugin = sr["get_task_registry"]().get(task_id)
    raw_text = input_path.read_text(encoding="utf-8")
    ingest = sr["ingest_validate_jsonl"](raw_text=raw_text, record_model=plugin.record_model)
    return ingest.valid, ingest.invalid, ingest.stats


def run_batch_triage(
    *,
    input_path: Path,
    output_path: Path,
    profile_id: str,
    structured_research_root: Path,
    runs_dir: Path,
    allow_invalid: bool = False,
) -> dict[str, Any]:
    sr = _load_structured_search()
    plugin = sr["get_task_registry"]().get("vuln_triage")
    valid_records, invalid_records, stats = load_valid_records(input_path, task_id="vuln_triage")
    if invalid_records and not allow_invalid:
        first = invalid_records[0]
        raise ValueError(
            f"Input contains {len(invalid_records)} invalid records; first error: "
            f"line={first.line_no} kind={first.kind} msg={first.message}"
        )

    deps = build_dependencies(structured_research_root, runs_dir)
    summary = sr["run_score"](
        task_id="vuln_triage",
        request=sr["RunScoreRequest"](
            profile_id=profile_id,
            records=valid_records,
            require_snapshot=False,
        ),
        plugin=plugin,
        deps=deps,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for record in summary.records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "loaded_lines": stats.total_lines,
        "schema_valid": stats.schema_ok,
        "schema_invalid": stats.schema_errors,
        "invalid_records": len(invalid_records),
        "scored_records": len(summary.records),
        "gate_passed": summary.gate_passed,
        "gate_failed": summary.gate_failed,
        "output_path": str(output_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic vuln_triage over a JSONL file.")
    parser.add_argument("--input", required=True, help="Path to FCE-style vulnerability JSONL.")
    parser.add_argument("--output", required=True, help="Path to scored JSONL output.")
    parser.add_argument(
        "--profile",
        dest="profile_id",
        default="high_severity_python",
        help="structured-research vuln_triage profile id.",
    )
    parser.add_argument(
        "--profile-id",
        dest="profile_id",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--structured-research-root",
        default=str(WORKSPACE_ROOT / "structured-research"),
        help="Path to the structured-research repository.",
    )
    parser.add_argument(
        "--runs-dir",
        default=str(WORKSPACE_ROOT / "structured-research" / "runs"),
        help="Path where structured-research run snapshots are written.",
    )
    parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Continue with valid records even if some JSONL lines are invalid.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_batch_triage(
            input_path=Path(args.input),
            output_path=Path(args.output),
            profile_id=args.profile_id,
            structured_research_root=Path(args.structured_research_root),
            runs_dir=Path(args.runs_dir),
            allow_invalid=args.allow_invalid,
        )
    except Exception as exc:
        parser.exit(1, f"{exc}\n")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
