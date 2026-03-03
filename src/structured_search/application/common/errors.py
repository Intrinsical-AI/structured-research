"""Application-level error markers for orchestration flows."""

from __future__ import annotations


class ApplicationError(RuntimeError):
    """Base error type for application orchestration failures."""


class SnapshotPersistenceError(ApplicationError):
    """Raised when snapshot persistence is required but cannot be completed."""
