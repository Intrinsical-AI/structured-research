"""Exporting adapters: ExportingPort implementations."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from structured_search.domain import BaseResult
from structured_search.ports.exporting import ExportingPort

logger = logging.getLogger(__name__)


class JSONLExporter(ExportingPort):
    """Export records to a JSONL file (one JSON object per line)."""

    def export(self, records: Sequence[BaseResult], path: Path | str) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.model_dump(mode="json")) + "\n")
        logger.info(f"Exported {len(records)} records to {file_path}")


class MockExporter(ExportingPort):
    """Mock exporter that stores records in memory (for testing)."""

    def __init__(self):
        self.records: list[BaseResult] = []

    def export(self, records: Sequence[BaseResult], path: Path | str) -> None:
        self.records = list(records)
