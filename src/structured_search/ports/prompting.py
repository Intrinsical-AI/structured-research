"""Prompt composition ports."""

from __future__ import annotations

from typing import Protocol


class PromptComposerPort(Protocol):
    """Contract for composing/loading prompt sections."""

    def load_base(self, sections: list[str] | None = None) -> str:
        """Load base prompt sections and return the assembled text."""

    def compose(
        self,
        task: str,
        step: str,
        profile: str | None = None,
        include_base: bool = True,
    ) -> str:
        """Compose a full prompt for a task/step/profile."""
