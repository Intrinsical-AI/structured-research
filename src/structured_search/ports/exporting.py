"""ExportingPort: interface for exporting records to destinations."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from structured_search.domain import BaseResult


class ExportingPort(ABC):
    """Port for exporting records to various formats.

    Implementations handle:
    - Serialization (JSON, CSV, etc.)
    - File writing
    - Format-specific options and metadata
    """

    @abstractmethod
    def export(self, records: Sequence[BaseResult], path: Path | str) -> None:
        """Export records to destination.

        Args:
            records: List of result records
            path: Destination path (file or directory)

        Raises:
            IOError: If write fails
            ValueError: If records are invalid for format
        """
        pass
