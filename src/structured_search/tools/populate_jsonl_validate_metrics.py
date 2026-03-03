"""Populate JSONL-validate metric events by calling the live HTTP endpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_GLOB = "results/job_search/**/results.jsonl"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000/v1",
        help="API base URL (with or without /v1)",
    )
    parser.add_argument(
        "--task-id",
        default="job_search",
        help="task_id path segment for /tasks/{task_id}/jsonl/validate",
    )
    parser.add_argument(
        "--profile-id",
        default="profile_example",
        help="profile_id sent to /tasks/{task_id}/jsonl/validate",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Explicit JSONL file path (repeatable)",
    )
    parser.add_argument(
        "--glob",
        default=DEFAULT_GLOB,
        help=f"Glob pattern used when no --input is provided (default: {DEFAULT_GLOB})",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Limit number of files processed (0 = all)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout per request in seconds",
    )
    return parser.parse_args(argv)


def normalize_api_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def collect_input_files(inputs: list[str], glob_pattern: str, max_files: int) -> list[Path]:
    files = [Path(p) for p in inputs] if inputs else sorted(Path(".").glob(glob_pattern))
    files = [p for p in files if p.is_file()]
    if max_files > 0:
        files = files[:max_files]
    return files


def call_validate_endpoint(
    *,
    api_base: str,
    task_id: str,
    profile_id: str,
    raw_jsonl: str,
    timeout: float,
) -> dict[str, Any]:
    url = f"{normalize_api_base(api_base)}/tasks/{task_id}/jsonl/validate"
    payload = {"profile_id": profile_id, "raw_jsonl": raw_jsonl}
    req = urllib_request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {url}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}: {body[:200]}") from exc


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    files = collect_input_files(args.input, args.glob, args.max_files)
    if not files:
        print("No input files found.")
        return 1

    total_lines = 0
    total_invalid = 0

    print(
        f"Using endpoint: {normalize_api_base(args.api_base)}/tasks/{args.task_id}/jsonl/validate"
    )
    print(
        f"Processing {len(files)} file(s) with task_id={args.task_id} profile_id={args.profile_id}"
    )

    for file_path in files:
        raw_jsonl = file_path.read_text(encoding="utf-8")
        response = call_validate_endpoint(
            api_base=args.api_base,
            task_id=args.task_id,
            profile_id=args.profile_id,
            raw_jsonl=raw_jsonl,
            timeout=args.timeout,
        )

        metrics = response.get("metrics", {}) if isinstance(response, dict) else {}
        file_total = int(metrics.get("total_lines", 0))
        file_invalid = int(metrics.get("invalid_lines", 0))
        total_lines += file_total
        total_invalid += file_invalid
        print(
            f"- {file_path}: total_lines={file_total}, invalid_lines={file_invalid}, "
            f"valid_records={len(response.get('valid_records', [])) if isinstance(response, dict) else 0}"
        )

    ratio = (total_invalid / total_lines) if total_lines else 0.0
    print("Done.")
    print(
        "Aggregate: "
        f"total_lines={total_lines}, invalid_lines={total_invalid}, invalid_ratio={ratio:.4f}"
    )
    print("Tip: run `make metrics-q2` to verify jsonl_parse_error_ratio now has data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
