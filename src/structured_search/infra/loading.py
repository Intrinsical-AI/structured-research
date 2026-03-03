"""Loading adapters: LoadingPort implementations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from structured_search.ports.loading import LoadingPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tolerant JSONL parser (does not abort on bad lines)
# ---------------------------------------------------------------------------


@dataclass
class ParseError:
    """A single line-level parse error from TolerantJSONLParser."""

    line_no: int
    raw_preview: str  # first 200 chars of the offending line
    kind: str  # "json_parse" | "not_object"
    message: str
    consumed_lines: int = 1


@dataclass
class ParsedRecord:
    """A parsed JSON object with source line metadata."""

    line_no: int
    record: dict
    consumed_lines: int = 1


class TolerantJSONLParser:
    """Parse JSONL without aborting on bad lines.

    Handles:
    - Standard JSONL (one JSON object per line)
    - Multi-line JSON objects (brace-depth counting, string-aware)
    - Non-object JSON values → collected as errors, not raised

    Returns (valid_records, errors) so callers can see what was recovered
    and what was skipped, without losing the whole batch.
    """

    def parse(
        self, text: str, max_continuation_lines: int = 30
    ) -> tuple[list[dict], list[ParseError]]:
        """Parse JSONL and return only parsed objects + parse errors.

        Use ``parse_with_lines`` when callers need line metadata for valid records.
        """
        parsed, errors = self.parse_with_lines(text, max_continuation_lines)
        return [item.record for item in parsed], errors

    def parse_with_lines(
        self, text: str, max_continuation_lines: int = 30
    ) -> tuple[list[ParsedRecord], list[ParseError]]:
        """Parse JSONL returning parsed objects with their starting line numbers."""
        valid: list[ParsedRecord] = []
        errors: list[ParseError] = []
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Fast path: single-line parse
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    errors.append(
                        ParseError(
                            i + 1,
                            line[:200],
                            "not_object",
                            f"Expected JSON object, got {type(obj).__name__}",
                            consumed_lines=1,
                        )
                    )
                else:
                    valid.append(ParsedRecord(i + 1, obj, consumed_lines=1))
                i += 1
                continue
            except json.JSONDecodeError:
                pass

            # Slow path: brace-depth accumulation for multi-line records
            obj, consumed, err = self._try_multiline(lines, i, max_continuation_lines)
            if obj is not None:
                valid.append(ParsedRecord(i + 1, obj, consumed_lines=max(consumed, 1)))
            else:
                errors.append(
                    ParseError(
                        i + 1,
                        line[:200],
                        "json_parse",
                        err,
                        consumed_lines=max(consumed, 1),
                    )
                )
            i += max(consumed, 1)

        return valid, errors

    def _try_multiline(
        self, lines: list[str], start: int, max_lines: int
    ) -> tuple[dict | None, int, str]:
        """Accumulate lines until braces balance, handling strings correctly.

        Returns (object_or_None, lines_consumed, error_message).
        """
        accumulated: list[str] = []
        depth = 0
        in_string = False
        escape_next = False

        for j in range(start, min(start + max_lines, len(lines))):
            line = lines[j]
            accumulated.append(line)
            depth, in_string, escape_next = self._scan_line_state(
                line=line,
                depth=depth,
                in_string=in_string,
                escape_next=escape_next,
            )
            if depth == 0 and accumulated:
                consumed = j - start + 1
                return self._parse_accumulated(accumulated, consumed)

        consumed = len(accumulated)
        obj, parsed_consumed, err = self._parse_accumulated(accumulated, consumed)
        if obj is not None:
            return obj, parsed_consumed, err
        if err:
            return None, parsed_consumed, err
        return None, 1, "Could not recover multi-line JSON object"

    @staticmethod
    def _scan_line_state(
        *,
        line: str,
        depth: int,
        in_string: bool,
        escape_next: bool,
    ) -> tuple[int, bool, bool]:
        for ch in line:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        return depth, in_string, escape_next

    @staticmethod
    def _parse_accumulated(accumulated: list[str], consumed: int) -> tuple[dict | None, int, str]:
        merged = "\n".join(accumulated)
        try:
            obj = json.loads(merged)
        except json.JSONDecodeError as exc:
            return None, consumed, str(exc)
        if isinstance(obj, dict):
            return obj, consumed, ""
        return None, consumed, f"Expected object, got {type(obj).__name__}"


class JSONLLoader(LoadingPort):
    """Load records from a JSONL file (one JSON object per line)."""

    def load(self, path: Path | str) -> list[dict]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        records: list[dict] = []
        with open(file_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError(f"Line {line_no}: expected object")
                    records.append(record)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Line {line_no}: invalid JSON: {e}") from e
        logger.info(f"Loaded {len(records)} records from {file_path}")
        return records


class MockLoader(LoadingPort):
    """Mock loader that returns fixed records (for testing)."""

    def __init__(self, records: list[dict] | None = None):
        self.records = records or []

    def load(self, path: Path | str) -> list[dict]:
        return self.records
