"""PromptComposer: load and assemble structured prompts from .md files.

Encapsulates the prompt file layout used in resources/prompts/:
  <prompts_dir>/_base/                          — invariant layers (identity, evidence, security, guardrails)
  <prompts_dir>/<task>/                         — task-specific context
  <prompts_dir>/<task>/profiles/<profile>/      — profile-level context override (optional)
  <prompts_dir>/<task>/steps/                   — step prompts (S0, S1, S2, S3, …)
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_SECTIONS = [
    "01_identity.md",
    "02_evidence.md",
    "03_security.md",
    "04_guardrails.md",
]

_SEPARATOR = "\n\n" + ("─" * 80) + "\n\n"


class PromptComposer:
    """Load and assemble structured prompts from a prompts directory.

    Usage:
        composer = PromptComposer(Path("resources/prompts"))
        identity = composer.load_base(sections=["01_identity.md"])
        full = composer.compose(task="job_search", step="S3")
    """

    def __init__(self, prompts_dir: Path | str):
        self.prompts_dir = Path(prompts_dir)

    def load_base(self, sections: list[str] | None = None) -> str:
        """Load base layer sections.

        Args:
            sections: Filenames to load (default: all 4 base sections).

        Returns:
            Concatenated text of requested sections.
        """
        names = sections if sections is not None else _BASE_SECTIONS
        parts: list[str] = []
        base_dir = self.prompts_dir / "_base"
        for name in names:
            path = base_dir / name
            if not path.exists():
                logger.warning(f"Base prompt section missing: {path}")
                continue
            parts.append(path.read_text(encoding="utf-8"))
        return _SEPARATOR.join(parts)

    def load_task_context(self, task: str) -> str:
        """Load the task-specific context file.

        Args:
            task: Task name (e.g. 'job_search').

        Returns:
            Content of <task>/context.md, or empty string if missing.
        """
        path = self.prompts_dir / task / "context.md"
        if not path.exists():
            logger.warning(f"Task context missing: {path}")
            return ""
        return path.read_text(encoding="utf-8")

    def load_profile_context(self, task: str, profile: str) -> str:
        """Load an optional profile-level context override.

        If the file exists it is appended after the task context, allowing
        profile-specific normalization rules, sources, or domain notes to
        supplement (not replace) the generic task context.

        Args:
            task: Task name (e.g. 'job_search').
            profile: Profile name (e.g. 'profile_1').

        Returns:
            Content of <task>/profiles/<profile>/context.md, or empty string.
        """
        path = self.prompts_dir / task / "profiles" / profile / "context.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def load_step(self, task: str, step: str) -> str:
        """Load a step prompt file.

        Args:
            task: Task name (e.g. 'job_search').
            step: Step code prefix (e.g. 'S3' matches 'S3_execute.md').

        Returns:
            Content of the matched step file, or empty string if missing.
        """
        step_dir = self.prompts_dir / task / "steps"
        matches = sorted(step_dir.glob(f"{step}*.md")) if step_dir.exists() else []
        if not matches:
            logger.warning(f"No step file found for {task}/{step} in {step_dir}")
            return ""
        return matches[0].read_text(encoding="utf-8")

    def compose(
        self,
        task: str,
        step: str,
        profile: str | None = None,
        include_base: bool = True,
    ) -> str:
        """Assemble a full prompt: base layers + task context + profile context + step.

        Args:
            task: Task name.
            step: Step code prefix.
            profile: Optional profile name for profile-level context override.
            include_base: Whether to include the base (_base/) sections.

        Returns:
            Full assembled prompt string.
        """
        parts: list[str] = []
        if include_base:
            base = self.load_base()
            if base:
                parts.append(base)
        context = self.load_task_context(task)
        if context:
            parts.append(context)
        if profile:
            profile_ctx = self.load_profile_context(task, profile)
            if profile_ctx:
                parts.append(profile_ctx)
        step_text = self.load_step(task, step)
        if step_text:
            parts.append(step_text)
        return _SEPARATOR.join(parts)
