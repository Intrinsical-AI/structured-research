"""LoadingPort: interface for loading records from sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Shared data types: produced by parsers, consumed by application services
# ---------------------------------------------------------------------------


@dataclass
class ParsedRecord:
    """A parsed JSON object with source line metadata."""

    line_no: int
    record: dict
    consumed_lines: int = 1


@dataclass
class ParseError:
    """A single line-level parse error from a JSONL parser."""

    line_no: int
    raw_preview: str  # first 200 chars of the offending line
    kind: Literal["json_parse", "not_object"]
    message: str
    consumed_lines: int = 1


# ---------------------------------------------------------------------------
# Port: tolerant JSONL text parsing
# ---------------------------------------------------------------------------


class JsonlTextParserPort(ABC):
    """Port for tolerant JSONL text parsing.

    Implementations handle multi-line recovery, error accumulation, and
    line-number tracking without aborting on malformed input.
    """

    @abstractmethod
    def parse_with_lines(self, text: str) -> tuple[list[ParsedRecord], list[ParseError]]:
        """Parse JSONL text and return (valid_records, errors) with line metadata.

        Returns:
            A tuple of (valid_records, errors). valid_records contains ParsedRecord
            instances for each successfully parsed JSON object. errors contains
            ParseError instances for each failed line.
        """
        ...


# ---------------------------------------------------------------------------
# Port: file-based record loading
# ---------------------------------------------------------------------------


class LoadingPort(ABC):
    """Port for loading raw records from various sources.

    Implementations handle:
    - File I/O (JSONL, JSON, CSV, etc.)
    - Format parsing and validation
    - Error handling and reporting
    """

    @abstractmethod
    def load(self, path: Path | str) -> list[dict]:
        """Load raw records from source.

        Args:
            path: Path to source file or directory

        Returns:
            List of dictionaries (raw records)

        Raises:
            FileNotFoundError: If path does not exist
            ValueError: If format is invalid
        """
        pass
