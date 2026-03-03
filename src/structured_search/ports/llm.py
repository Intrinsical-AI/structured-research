"""LLMPort: interface for LLM implementations."""

from abc import ABC, abstractmethod
from typing import Any


class LLMPort(ABC):
    """Port for interacting with LLM services.

    Implementations handle:
    - API calls (OpenAI, Ollama, Claude, etc.)
    - Prompt formatting and chunking
    - Response parsing and validation
    - Structured output (JSON schema)
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Call LLM and get text response.

        Args:
            prompt: Full prompt text
            **kwargs: Implementation-specific options (temperature, top_p, etc.)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If LLM call fails
        """
        pass

    @abstractmethod
    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        """Call LLM expecting JSON output matching Pydantic schema.

        Args:
            prompt: Full prompt text
            schema: Pydantic model class to validate against
            **kwargs: Implementation-specific options

        Returns:
            Parsed dictionary matching schema

        Raises:
            RuntimeError: If LLM call fails
            ValueError: If response doesn't match schema
        """
        pass
