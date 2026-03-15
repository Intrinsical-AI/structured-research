"""LLM adapters: OllamaLLM, AnthropicLLM, OpenAILLM, GeminiLLM, OpenRouterLLM, MockLLM."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, ValidationError

from structured_search.ports.llm import LLMPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK imports
# ---------------------------------------------------------------------------

try:
    import anthropic as _anthropic_sdk

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from openai import OpenAI as _OpenAI

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

try:
    from google import genai as _genai

    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _parse_json_from_text(raw: str, schema: type) -> dict:
    """Extract and validate JSON from raw LLM text. Shared by all adapters."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
        else:
            raise ValueError(f"No JSON found in response: {raw[:200]}") from exc
    if issubclass(schema, BaseModel):
        try:
            return schema.model_validate(data).model_dump()
        except ValidationError as e:
            raise ValueError(f"Response doesn't match schema {schema.__name__}: {e}") from e
    return data


# ---------------------------------------------------------------------------
# OllamaLLM — pure HTTP, no LangChain
# ---------------------------------------------------------------------------


class OllamaLLM(LLMPort):
    """LLM adapter for Ollama via direct HTTP (no LangChain dependency)."""

    def __init__(
        self,
        model: str = "lfm2.5-thinking",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            return self._invoke_via_http_chat(
                prompt,
                temperature=kwargs.get("temperature", self.temperature),
                num_predict=kwargs.get("num_predict"),
                timeout=kwargs.get("timeout"),
            )
        except Exception as e:
            msg = str(e)
            hint = ""
            if "model" in msg.lower() and "not found" in msg.lower():
                hint = f" (hint: run `ollama pull {self.model}`)"
            raise RuntimeError(
                f"Ollama generation failed for model={self.model} "
                f"at base_url={self.base_url}: {msg}{hint}"
            ) from e

    def _invoke_via_http_chat(
        self,
        prompt: str,
        temperature: float,
        num_predict: int | None = None,
        timeout: int | float | None = None,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        timeout_seconds = (
            timeout if timeout is not None else _env_positive_int("OLLAMA_TIMEOUT_SECONDS", 120)
        )
        payload = self._build_http_chat_payload(prompt, temperature, num_predict)
        raw = self._send_http_chat_request(url, timeout_seconds, payload)
        return self._decode_http_chat_response(raw, url)

    def _build_http_chat_payload(
        self,
        prompt: str,
        temperature: float,
        num_predict: int | None,
    ) -> dict[str, Any]:
        resolved_num_predict = (
            num_predict
            if num_predict is not None
            else _env_positive_int("OLLAMA_NUM_PREDICT", 256)
        )
        options: dict[str, Any] = {"temperature": temperature}
        if resolved_num_predict > 0:
            options["num_predict"] = resolved_num_predict
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": options,
        }

    @staticmethod
    def _send_http_chat_request(
        url: str, timeout_seconds: int | float, payload: dict[str, Any]
    ) -> str:
        req = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib_error.HTTPError as e:
            details = ""
            try:
                details = e.read().decode("utf-8")
            except Exception:  # pragma: no cover
                details = str(e)
            raise RuntimeError(f"Ollama HTTP error status={e.code} url={url}: {details}") from e
        except urllib_error.URLError as e:
            raise RuntimeError(f"Ollama HTTP connect failed url={url}: {e}") from e
        except TimeoutError as e:
            raise RuntimeError(f"Ollama HTTP timeout url={url}: {e}") from e

    @staticmethod
    def _decode_http_chat_response(raw: str, url: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama returned invalid JSON from url={url}: {raw[:200]}") from e
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if content is not None:
                return str(content)
        response_text = data.get("response")
        if isinstance(response_text, str):
            return response_text
        raise RuntimeError("Ollama HTTP response missing message.content/response field")

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only. No markdown, no explanation."
        try:
            raw = self.generate(json_prompt, **kwargs)
            return _parse_json_from_text(raw, schema)
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"Ollama extract_json failed: {e}") from e


# ---------------------------------------------------------------------------
# AnthropicLLM
# ---------------------------------------------------------------------------


class AnthropicLLM(LLMPort):
    """LLM adapter for Anthropic Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ):
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. Run: pip install 'structured-search[anthropic]'"
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = _anthropic_sdk.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                temperature=kwargs.get("temperature", self.temperature),
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Anthropic generation failed for model={self.model}: {e}") from e

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only. No markdown, no explanation."
        try:
            raw = self.generate(json_prompt, **kwargs)
            return _parse_json_from_text(raw, schema)
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"Anthropic extract_json failed: {e}") from e


# ---------------------------------------------------------------------------
# OpenAILLM
# ---------------------------------------------------------------------------


class OpenAILLM(LLMPort):
    """LLM adapter for OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ):
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. Run: pip install 'structured-search[openai]'"
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = _OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"OpenAI generation failed for model={self.model}: {e}") from e

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only. No markdown, no explanation."
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                messages=[{"role": "user", "content": json_prompt}],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return _parse_json_from_text(raw, schema)
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"OpenAI extract_json failed: {e}") from e


# ---------------------------------------------------------------------------
# GeminiLLM
# ---------------------------------------------------------------------------


class GeminiLLM(LLMPort):
    """LLM adapter for Google Gemini API (google-genai SDK)."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ):
        if not _GEMINI_AVAILABLE:
            raise ImportError(
                "google-genai package not installed. Run: pip install 'structured-search[gemini]'"
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = _genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
                },
            )
            return response.text or ""
        except Exception as e:
            raise RuntimeError(f"Gemini generation failed for model={self.model}: {e}") from e

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only. No markdown, no explanation."
        try:
            raw = self.generate(json_prompt, **kwargs)
            return _parse_json_from_text(raw, schema)
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"Gemini extract_json failed: {e}") from e


# ---------------------------------------------------------------------------
# OpenRouterLLM
# ---------------------------------------------------------------------------


class OpenRouterLLM(LLMPort):
    """LLM adapter for OpenRouter (OpenAI-compatible endpoint, separate credentials)."""

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-6",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
        site_url: str | None = None,
        site_name: str | None = None,
    ):
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed (used as OpenRouter HTTP client). "
                "Run: pip install 'structured-search[openrouter]'"
            )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        extra_headers: dict[str, str] = {}
        resolved_site_url = site_url or os.getenv("OPENROUTER_SITE_URL")
        resolved_site_name = site_name or os.getenv("OPENROUTER_SITE_NAME")
        if resolved_site_url:
            extra_headers["HTTP-Referer"] = resolved_site_url
        if resolved_site_name:
            extra_headers["X-Title"] = resolved_site_name
        self._client = _OpenAI(
            base_url=self._BASE_URL,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY"),
            default_headers=extra_headers or None,
        )

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"OpenRouter generation failed for model={self.model}: {e}") from e

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only. No markdown, no explanation."
        try:
            raw = self.generate(json_prompt, **kwargs)
            return _parse_json_from_text(raw, schema)
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"OpenRouter extract_json failed: {e}") from e


# ---------------------------------------------------------------------------
# MockLLM
# ---------------------------------------------------------------------------


class MockLLM(LLMPort):
    """Mock LLM returning fixed responses (for testing)."""

    def __init__(self, text_response: str = "Mock response", json_response: dict | None = None):
        self.text_response = text_response
        self.json_response = json_response or {}
        self.generate_calls: list = []
        self.extract_json_calls: list = []

    def generate(self, prompt: str, **kwargs: Any) -> str:
        self.generate_calls.append((prompt, kwargs))
        return self.text_response

    def extract_json(self, prompt: str, schema: type, **kwargs: Any) -> dict:
        self.extract_json_calls.append((prompt, schema, kwargs))
        return self.json_response


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "lfm2.5-thinking",
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "openrouter": "anthropic/claude-sonnet-4-6",
}

SUPPORTED_PROVIDERS: frozenset[str] = frozenset(_PROVIDER_DEFAULTS)


def build_llm(
    provider: str,
    model: str | None = None,
    *,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
) -> LLMPort:
    """Instantiate the correct LLMPort adapter for the given provider.

    Providers: ollama | anthropic | openai | gemini | openrouter
    """
    resolved_model = model or _PROVIDER_DEFAULTS.get(provider, "")
    match provider:
        case "ollama":
            return OllamaLLM(
                model=resolved_model,
                base_url=base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434",
                temperature=temperature,
            )
        case "anthropic":
            return AnthropicLLM(
                model=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            )
        case "openai":
            return OpenAILLM(
                model=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key or os.getenv("OPENAI_API_KEY"),
            )
        case "gemini":
            return GeminiLLM(
                model=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key or os.getenv("GEMINI_API_KEY"),
            )
        case "openrouter":
            return OpenRouterLLM(
                model=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key or os.getenv("OPENROUTER_API_KEY"),
                **kwargs,
            )
        case _:
            raise ValueError(
                f"Unknown LLM provider: {provider!r}. "
                f"Valid: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
