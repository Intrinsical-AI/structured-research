"""LLM adapters: OllamaLLM, MockLLM."""

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

try:
    from langchain_ollama import ChatOllama as _LangChainChatOllama

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class OllamaLLM(LLMPort):
    """LLM adapter for Ollama chat completions via LangChain ChatOllama."""

    def __init__(
        self,
        model: str = "lfm2.5-thinking",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
    ):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.llm = None
        if _LANGCHAIN_AVAILABLE:
            try:
                self.llm = _LangChainChatOllama(
                    model=model, base_url=base_url, temperature=temperature
                )
                logger.info(f"Ollama ChatOllama ready: {model} @ {base_url}")
            except Exception as e:
                raise RuntimeError(f"Ollama connect failed: {e}") from e
        else:
            logger.warning("langchain_ollama not installed; using direct Ollama HTTP client")

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            if self.llm is not None and kwargs:
                llm = _LangChainChatOllama(
                    model=self.model,
                    base_url=self.base_url,
                    temperature=kwargs.get("temperature", self.temperature),
                )
                return self._coerce_chat_content(llm.invoke(prompt))
            if self.llm is not None:
                return self._coerce_chat_content(self.llm.invoke(prompt))
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

    @staticmethod
    def _coerce_chat_content(response: Any) -> str:
        """Normalize ChatOllama response content into plain text."""
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
                elif isinstance(part, str):
                    chunks.append(part)
            return "".join(chunks)
        return str(content)

    def _invoke_via_http_chat(
        self,
        prompt: str,
        temperature: float,
        num_predict: int | None = None,
        timeout: int | float | None = None,
    ) -> str:
        base = self.base_url.rstrip("/")
        url = f"{base}/api/chat"
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
        request = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib_error.HTTPError as e:
            details = ""
            try:
                details = e.read().decode("utf-8")
            except Exception:  # pragma: no cover - defensive best effort
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
        try:
            if self.llm is not None and issubclass(schema, BaseModel):
                try:
                    structured_llm = self.llm.with_structured_output(schema)
                    result = structured_llm.invoke(prompt)
                    if isinstance(result, BaseModel):
                        return result.model_dump()
                    if isinstance(result, dict):
                        return schema.model_validate(result).model_dump()
                    return schema.model_validate(result).model_dump()
                except Exception as e:
                    logger.warning(
                        "Structured output failed; falling back to raw JSON parse: %s",
                        e,
                    )

            raw = self.generate(prompt, **kwargs)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    data = json.loads(m.group())
                else:
                    raise ValueError(f"No JSON found in response: {raw[:200]}") from exc
            if issubclass(schema, BaseModel):
                return schema.model_validate(data).model_dump()
            return data
        except ValidationError as e:
            raise ValueError(f"Response doesn't match schema: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama extract_json failed: {e}") from e


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
