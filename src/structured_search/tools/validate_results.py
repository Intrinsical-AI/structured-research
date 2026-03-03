"""Validate and compile results from LLM extractions."""

import argparse
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def validate_results(
    input_dir: str,
    output_dir: str,
    task: str = "job_search",
    strict: bool = False,
) -> int:
    """Validate all JSON/JSONL files in input_dir.

    Outputs:
    - results.jsonl (valid records)
    - invalid.jsonl (rejected with error reasons)
    - metrics.json (stats)

    Args:
        input_dir: Input directory with raw results
        output_dir: Output directory for validated results
        task: Task name (job_search, gen_cv, product_search)
        strict: If True, fail on first error; else collect all

    Returns:
        0 on success, 1 on error
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        logger.error(f"Input directory not found: {input_path}")
        return 1

    output_path.mkdir(parents=True, exist_ok=True)

    results_file = output_path / "results.jsonl"
    invalid_file = output_path / "invalid.jsonl"
    metrics_file = output_path / "metrics.json"

    model = _select_model(task)
    if model is None:
        logger.error(f"Unknown task: {task}. Supported: job_search, gen_cv, product_search")
        return 1

    valid_count = 0
    invalid_count = 0
    errors = []

    logger.info(f"Validating {task} results from {input_path}")

    # Truncate output artifacts on each run to avoid stale/duplicated records.
    with (
        open(results_file, "w", encoding="utf-8") as valid_f,
        open(invalid_file, "w", encoding="utf-8") as invalid_f,
    ):
        # Process all JSON and JSONL files
        for json_file in list(input_path.glob("*.json")) + list(input_path.glob("*.jsonl")):
            logger.info(f"Processing {json_file.name}")
            status, valid_delta, invalid_delta = _process_file_records(
                json_file=json_file,
                model=model,
                valid_f=valid_f,
                invalid_f=invalid_f,
                errors=errors,
                strict=strict,
            )
            valid_count += valid_delta
            invalid_count += invalid_delta
            if status == "failed":
                return 1

    # Write metrics
    metrics = {
        "valid": valid_count,
        "invalid": invalid_count,
        "total": valid_count + invalid_count,
        "errors": errors if errors else None,
    }

    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Validation Results for {task}")
    print(f"{'=' * 60}")
    print(f"✓ Valid:   {valid_count}")
    print(f"✗ Invalid: {invalid_count}")
    print(f"Total:   {valid_count + invalid_count}")
    print("\nOutputs:")
    print(f"  ✓ {results_file}")
    if invalid_count > 0:
        print(f"  ✗ {invalid_file}")
    print(f"  📊 {metrics_file}")

    return 0


def _select_model(task: str):
    if task == "job_search":
        from structured_search.domain.job_search.models import JobPosting

        return JobPosting
    if task == "gen_cv":
        from structured_search.domain.gen_cv.models import JobDescription

        return JobDescription
    if task == "product_search":
        from structured_search.domain.product_search.models import ProductRecord

        return ProductRecord
    return None


def _write_invalid_record(
    invalid_f,
    *,
    error_msg: str,
    raw_record: dict | None,
) -> None:
    invalid_f.write(
        json.dumps(
            {"error": error_msg, "record": raw_record},
            ensure_ascii=False,
        )
        + "\n"
    )


def _process_file_records(
    *,
    json_file: Path,
    model,
    valid_f,
    invalid_f,
    errors: list[str],
    strict: bool,
) -> tuple[str, int, int]:
    valid_count = 0
    invalid_count = 0
    for line_no, raw_record in read_records(json_file):
        if isinstance(raw_record, json.JSONDecodeError):
            invalid_count += 1
            error_msg = f"{json_file.name}:{line_no}: JSON parse error: {raw_record}"
            errors.append(error_msg)
            _write_invalid_record(invalid_f, error_msg=error_msg, raw_record=None)
            if strict:
                logger.error(error_msg)
                return "failed", valid_count, invalid_count
            continue
        try:
            record = model.model_validate(raw_record)
            record_dict = record.model_dump(mode="json")
            valid_f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
            valid_count += 1
        except Exception as exc:
            invalid_count += 1
            error_msg = f"{json_file.name}:{line_no}: {exc!s}"
            errors.append(error_msg)
            _write_invalid_record(invalid_f, error_msg=error_msg, raw_record=raw_record)
            if strict:
                logger.error(error_msg)
                return "failed", valid_count, invalid_count
    return "ok", valid_count, invalid_count


# Only match Markdown links where the visible text is a URL (starts with http).
# This avoids false-positives on JSON arrays like [{"id": ...}](...).
_MD_LINK_RE = re.compile(r"\[(https?://[^\]]*)\]\([^)]*\)")


def _sanitize_line(raw: str) -> str:
    """Best-effort cleanup of common LLM JSON mistakes on a single line.

    Applied *before* ``json.loads`` so that recoverable errors don't cause
    parse failures.

    Fixes applied (in order):
    1. Markdown link syntax ``[text](href)`` → ``text``
    2. Missing commas: ``} "`` → ``}, "`` (LLMs drop commas between fields)
    """
    # 1. Markdown URLs → plain text (the link text is the actual URL)
    out = _MD_LINK_RE.sub(r"\1", raw)
    # 2. Missing comma after closing brace before a new key or object
    #    Only inject comma when one is genuinely absent (negative lookbehind
    #    for comma ensures we don't double-comma already-correct JSON).
    out = re.sub(r"\}(?!\s*,)\s*\"", '}, "', out)
    out = re.sub(r"\}(?!\s*,)\s*\{", "}, {", out)
    return out


def read_records(file_path: Path):
    """Read records from JSON or JSONL file.

    Applies lightweight sanitisation (Markdown URL stripping) before parsing.
    Yields ``(line_no, record_dict)`` tuples for JSONL, or ``(1, record)`` for
    plain JSON.  On ``JSONDecodeError`` yields ``(line_no, error)`` so the
    caller can handle it without crashing.

    Args:
        file_path: Path to JSON or JSONL file

    Yields:
        Tuples of (line_number, dict | JSONDecodeError)
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read().strip()

        if file_path.suffix == ".jsonl":
            for line_no, line in enumerate(content.split("\n"), start=1):
                if not line.strip():
                    continue
                try:
                    yield line_no, json.loads(_sanitize_line(line))
                except json.JSONDecodeError as exc:
                    yield line_no, exc
        else:
            sanitized = _sanitize_line(content)
            try:
                data = json.loads(sanitized)
            except json.JSONDecodeError as exc:
                yield 1, exc
                return
            if isinstance(data, list):
                yield from enumerate(data, start=1)
            else:
                yield 1, data


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and validate results."""
    parser = argparse.ArgumentParser(description="Validate and compile LLM extraction results")
    parser.add_argument("--input-dir", required=True, help="Input directory")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument(
        "--task",
        default="job_search",
        help="Task name (job_search, gen_cv, product_search)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on first error",
    )

    args = parser.parse_args(argv)

    return validate_results(
        args.input_dir,
        args.output_dir,
        args.task,
        args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
