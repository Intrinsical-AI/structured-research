"""Generic tolerant JSONL ingest + schema validation for task plugins."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from structured_search.application.common.dependencies import (
    ApplicationDependencies,
    resolve_dependencies,
)
from structured_search.application.common.validation_messages import format_schema_validation_error
from structured_search.contracts import IngestError, IngestResult, IngestStats


def ingest_validate_jsonl(
    *,
    raw_text: str,
    record_model: type[BaseModel],
    deps: ApplicationDependencies | None = None,
) -> IngestResult:
    resolved = resolve_dependencies(deps)
    parsed_valid, parse_errors = resolved.jsonl_parser.parse_with_lines(raw_text)

    errors: list[IngestError] = [
        IngestError(
            line_no=e.line_no,
            raw_preview=e.raw_preview,
            kind=e.kind,
            message=e.message,
        )
        for e in parse_errors
    ]

    valid_records: list[dict[str, Any]] = []
    schema_error_count = 0
    for parsed in parsed_valid:
        raw = parsed.record
        try:
            record_model.model_validate(raw)
            valid_records.append(raw)
        except ValidationError as exc:
            schema_error_count += 1
            errors.append(
                IngestError(
                    line_no=parsed.line_no,
                    raw_preview=json.dumps(raw, ensure_ascii=False)[:200],
                    kind="schema_validation",
                    message=format_schema_validation_error(exc),
                )
            )

    parse_ok_lines = sum(item.consumed_lines for item in parsed_valid)
    parse_error_lines = sum(item.consumed_lines for item in parse_errors)
    total_lines = parse_ok_lines + parse_error_lines

    stats = IngestStats(
        total_lines=total_lines,
        parse_ok=parse_ok_lines,
        schema_ok=len(valid_records),
        parse_errors=parse_error_lines,
        schema_errors=schema_error_count,
    )
    return IngestResult(valid=valid_records, invalid=errors, stats=stats)
