"""Input sanitization helpers for job-search JSONL ETL runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

_MD_LINK_RE = re.compile(r"^\[(https?://[^\]]+)\]\([^)]*\)$")


@dataclass(frozen=True)
class SanitizeSummary:
    total_lines: int
    parsed_objects: int
    parse_errors: int
    non_object_lines: int
    touched_records: int
    fixed_fields: int
    output_path: Path
    used_temp_file: bool


def sanitize_jsonl_for_run(input_path: Path | str) -> SanitizeSummary:
    """Sanitize a JSONL file for `job-search run`.

    Behavior:
    - Applies best-effort fixes only to parseable JSON-object lines.
    - Leaves valid lines untouched when no fixes are needed.
    - Leaves unparseable lines untouched (idempotent for corrupt input).
    - Writes a temp sanitized file only when at least one line changes.
    """
    source = Path(input_path)
    lines_out: list[str] = []
    needs_rewrite = False

    total_lines = 0
    parsed_objects = 0
    parse_errors = 0
    non_object_lines = 0
    touched_records = 0
    fixed_fields = 0

    with source.open(encoding="utf-8") as f:
        for raw_line in f:
            total_lines += 1
            stripped = raw_line.strip()
            if not stripped:
                lines_out.append(raw_line)
                continue

            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parse_errors += 1
                lines_out.append(raw_line)
                continue

            if not isinstance(parsed, dict):
                non_object_lines += 1
                lines_out.append(raw_line)
                continue

            parsed_objects += 1
            changes = _sanitize_record(parsed)
            if changes == 0:
                lines_out.append(raw_line)
                continue

            needs_rewrite = True
            touched_records += 1
            fixed_fields += changes
            lines_out.append(json.dumps(parsed, ensure_ascii=False) + "\n")

    if not needs_rewrite:
        return SanitizeSummary(
            total_lines=total_lines,
            parsed_objects=parsed_objects,
            parse_errors=parse_errors,
            non_object_lines=non_object_lines,
            touched_records=0,
            fixed_fields=0,
            output_path=source,
            used_temp_file=False,
        )

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f"{source.stem}.sanitized.",
        suffix=".jsonl",
        delete=False,
    ) as tmp:
        tmp.writelines(lines_out)
        temp_path = Path(tmp.name)

    return SanitizeSummary(
        total_lines=total_lines,
        parsed_objects=parsed_objects,
        parse_errors=parse_errors,
        non_object_lines=non_object_lines,
        touched_records=touched_records,
        fixed_fields=fixed_fields,
        output_path=temp_path,
        used_temp_file=True,
    )


def _sanitize_record(record: dict[str, Any]) -> int:
    changes = 0

    for field in ("apply_url", "source"):
        cleaned = _clean_url(record.get(field))
        if cleaned != record.get(field):
            record[field] = cleaned
            changes += 1

    if record.get("stack", "__MISSING__") is None:
        record["stack"] = []
        changes += 1

    evidence = record.get("evidence")
    if isinstance(evidence, list):
        for entry in evidence:
            if not isinstance(entry, dict):
                continue
            cleaned = _clean_url(entry.get("url"))
            if cleaned != entry.get("url"):
                entry["url"] = cleaned
                changes += 1

            locator = entry.get("locator")
            if not isinstance(locator, dict):
                continue

            changes += _coerce_alias_key(locator, "value")
            if "value" not in locator or locator.get("value") is None:
                locator["value"] = ""
                changes += 1
            elif not isinstance(locator.get("value"), str):
                locator["value"] = str(locator["value"])
                changes += 1

    facts = record.get("facts")
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict):
                changes += _coerce_alias_key(fact, "value")

    inferences = record.get("inferences")
    if isinstance(inferences, list):
        for inference in inferences:
            if isinstance(inference, dict):
                changes += _coerce_alias_key(inference, "value")

    return changes


def _clean_url(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    markdown_link = _MD_LINK_RE.match(text)
    if markdown_link:
        return markdown_link.group(1)
    if text.startswith("[http://") or text.startswith("[https://"):
        return text.lstrip("[")
    return value


def _coerce_alias_key(payload: dict[str, Any], target_key: str) -> int:
    if target_key in payload:
        return 0

    for key in list(payload.keys()):
        normalized = "".join(ch for ch in str(key).strip().lower() if ch.isalpha())
        if normalized.startswith(target_key):
            payload[target_key] = payload[key]
            del payload[key]
            return 1
    return 0
