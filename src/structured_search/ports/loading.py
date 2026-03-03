"""LoadingPort: interface for loading records from sources."""

from abc import ABC, abstractmethod
from pathlib import Path


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
