"""Unit tests for infra.llm adapters and build_llm factory."""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
from pydantic import BaseModel

from structured_search.infra import llm as llm_module
from structured_search.infra.llm import (
    AnthropicLLM,
    GeminiLLM,
    MockLLM,
    OllamaLLM,
    OpenAILLM,
    OpenRouterLLM,
    build_llm,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_urlopen(payload: str):
    """Return a factory that produces a fake urlopen responding with payload."""

    class _FakeResponse:
        def read(self):
            return payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _opener(request, timeout=60):
        _ = timeout, request
        return _FakeResponse()

    return _opener


# ---------------------------------------------------------------------------
# OllamaLLM — HTTP path (no LangChain)
# ---------------------------------------------------------------------------


def test_ollama_generate_sends_correct_payload(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b'{"message":{"content":"hello"}}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_urlopen(request, timeout=60):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _fake_urlopen)

    llm = OllamaLLM(model="llama3.1", base_url="http://localhost:11434")
    result = llm.generate("ping")

    assert result == "hello"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == "llama3.1"
    assert captured["body"]["messages"][0]["content"] == "ping"
    assert captured["body"]["stream"] is False


def test_ollama_generate_decodes_response_field_fallback(monkeypatch):
    monkeypatch.setattr(
        llm_module.urllib_request,
        "urlopen",
        _fake_urlopen('{"response":"alt response"}'),
    )
    llm = OllamaLLM(model="m")
    assert llm.generate("q") == "alt response"


def test_ollama_generate_wraps_runtime_error(monkeypatch):
    def _boom(_request, timeout=60):
        raise RuntimeError("upstream failure")

    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _boom)
    llm = OllamaLLM(model="m")
    with pytest.raises(RuntimeError, match="Ollama generation failed"):
        llm.generate("ping")


def test_ollama_generate_model_not_found_hint(monkeypatch):
    def _boom(_request, timeout=60):
        raise RuntimeError("model 'foo' not found")

    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _boom)
    llm = OllamaLLM(model="foo")
    with pytest.raises(RuntimeError, match=r"hint: run `ollama pull foo`"):
        llm.generate("ping")


def test_ollama_extract_json_appends_json_instruction(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b'{"message":{"content":"{\\"summary\\": \\"ok\\"}"}}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_urlopen(request, timeout=60):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _fake_urlopen)

    class _Schema(BaseModel):
        summary: str

    llm = OllamaLLM(model="m")
    result = llm.extract_json("Give me JSON", _Schema)
    assert result == {"summary": "ok"}
    assert "valid JSON only" in captured["body"]["messages"][0]["content"]


def test_ollama_extract_json_regex_fallback(monkeypatch):
    raw_response = 'Here is the result: {"summary": "extracted"} done.'
    monkeypatch.setattr(
        llm_module.urllib_request,
        "urlopen",
        _fake_urlopen(json.dumps({"message": {"content": raw_response}})),
    )

    class _Schema(BaseModel):
        summary: str

    llm = OllamaLLM(model="m")
    # The content with embedded JSON in a prose response should still parse
    result = llm.extract_json("prompt", _Schema)
    assert result["summary"] == "extracted"


# ---------------------------------------------------------------------------
# AnthropicLLM
# ---------------------------------------------------------------------------


def test_anthropic_raises_import_error_when_sdk_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "_ANTHROPIC_AVAILABLE", False)
    with pytest.raises(ImportError, match="anthropic package not installed"):
        AnthropicLLM(model="claude-sonnet-4-6")


def test_anthropic_generate_calls_messages_create(monkeypatch):
    class _FakeContent:
        text = "anthropic response"

    class _FakeMessage:
        content: ClassVar[list] = [_FakeContent()]

    class _FakeMessages:
        def create(self, **kwargs):
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(llm_module, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(
        llm_module,
        "_anthropic_sdk",
        type("_sdk", (), {"Anthropic": staticmethod(lambda **_: _FakeClient())})(),
    )

    llm = AnthropicLLM(model="claude-sonnet-4-6", api_key="test-key")
    assert llm.generate("hello") == "anthropic response"


def test_anthropic_generate_wraps_exception(monkeypatch):
    class _FakeMessages:
        def create(self, **kwargs):
            raise RuntimeError("quota exceeded")

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(llm_module, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(
        llm_module,
        "_anthropic_sdk",
        type("_sdk", (), {"Anthropic": staticmethod(lambda **_: _FakeClient())})(),
    )

    llm = AnthropicLLM(model="claude-sonnet-4-6", api_key="key")
    with pytest.raises(RuntimeError, match="Anthropic generation failed"):
        llm.generate("ping")


def test_anthropic_extract_json_appends_json_instruction(monkeypatch):
    captured: dict = {}

    class _FakeContent:
        text = '{"result": "ok"}'

    class _FakeMessage:
        content: ClassVar[list] = [_FakeContent()]

    class _FakeMessages:
        def create(self, **kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(llm_module, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(
        llm_module,
        "_anthropic_sdk",
        type("_sdk", (), {"Anthropic": staticmethod(lambda **_: _FakeClient())})(),
    )

    class _Schema(BaseModel):
        result: str

    llm = AnthropicLLM(model="m", api_key="key")
    out = llm.extract_json("original prompt", _Schema)
    assert out == {"result": "ok"}
    assert "valid JSON only" in captured["prompt"]


# ---------------------------------------------------------------------------
# OpenAILLM
# ---------------------------------------------------------------------------


def test_openai_raises_import_error_when_sdk_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", False)
    with pytest.raises(ImportError, match="openai package not installed"):
        OpenAILLM(model="gpt-4o")


def test_openai_generate_calls_chat_completions(monkeypatch):
    class _FakeMessage:
        content = "openai response"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeCompletion:
        choices: ClassVar[list] = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            return _FakeCompletion()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_OpenAI", lambda **_: _FakeClient())

    llm = OpenAILLM(model="gpt-4o", api_key="key")
    assert llm.generate("hello") == "openai response"


def test_openai_extract_json_uses_json_object_format(monkeypatch):
    captured: dict = {}

    class _FakeMessage:
        content = '{"value": 42}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeCompletion:
        choices: ClassVar[list] = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            captured["response_format"] = kwargs.get("response_format")
            return _FakeCompletion()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_OpenAI", lambda **_: _FakeClient())

    class _Schema(BaseModel):
        value: int

    llm = OpenAILLM(model="gpt-4o", api_key="key")
    result = llm.extract_json("prompt", _Schema)
    assert result == {"value": 42}
    assert captured["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# GeminiLLM
# ---------------------------------------------------------------------------


def test_gemini_raises_import_error_when_sdk_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "_GEMINI_AVAILABLE", False)
    with pytest.raises(ImportError, match="google-genai package not installed"):
        GeminiLLM(model="gemini-2.0-flash")


def test_gemini_generate_calls_models_generate_content(monkeypatch):
    class _FakeResponse:
        text = "gemini response"

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(llm_module, "_GEMINI_AVAILABLE", True)
    monkeypatch.setattr(
        llm_module,
        "_genai",
        type("_sdk", (), {"Client": staticmethod(lambda **_: _FakeClient())})(),
    )

    llm = GeminiLLM(model="gemini-2.0-flash", api_key="key")
    assert llm.generate("hello") == "gemini response"


def test_gemini_generate_wraps_exception(monkeypatch):
    class _FakeModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("rate limited")

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(llm_module, "_GEMINI_AVAILABLE", True)
    monkeypatch.setattr(
        llm_module,
        "_genai",
        type("_sdk", (), {"Client": staticmethod(lambda **_: _FakeClient())})(),
    )

    llm = GeminiLLM(model="m", api_key="key")
    with pytest.raises(RuntimeError, match="Gemini generation failed"):
        llm.generate("ping")


# ---------------------------------------------------------------------------
# OpenRouterLLM
# ---------------------------------------------------------------------------


def test_openrouter_raises_import_error_when_sdk_missing(monkeypatch):
    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", False)
    with pytest.raises(ImportError, match="openai package not installed"):
        OpenRouterLLM(model="anthropic/claude-sonnet-4-6")


def test_openrouter_uses_openrouter_base_url(monkeypatch):
    captured: dict = {}

    class _FakeMessage:
        content = "router response"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeCompletion:
        choices: ClassVar[list] = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            return _FakeCompletion()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    def _fake_openai(*, base_url, api_key, default_headers=None):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return _FakeClient()

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_OpenAI", _fake_openai)

    llm = OpenRouterLLM(model="anthropic/claude-sonnet-4-6", api_key="or-key")
    assert llm.generate("hi") == "router response"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "or-key"


def test_openrouter_injects_site_headers(monkeypatch):
    captured: dict = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _M:
                        content = "ok"

                    class _C:
                        message = _M()

                    class _R:
                        choices: ClassVar[list] = [_C()]

                    return _R()

    def _fake_openai(*, base_url, api_key, default_headers=None):
        captured["headers"] = default_headers
        return _FakeClient()

    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_OpenAI", _fake_openai)

    OpenRouterLLM(model="m", api_key="k", site_url="https://myapp.com", site_name="MyApp")
    assert captured["headers"]["HTTP-Referer"] == "https://myapp.com"
    assert captured["headers"]["X-Title"] == "MyApp"


# ---------------------------------------------------------------------------
# MockLLM
# ---------------------------------------------------------------------------


def test_mock_llm_records_generate_calls():
    llm = MockLLM(text_response="hello")
    result = llm.generate("prompt one", temperature=0.5)
    assert result == "hello"
    assert llm.generate_calls == [("prompt one", {"temperature": 0.5})]


def test_mock_llm_records_extract_json_calls():
    class _S(BaseModel):
        x: int

    llm = MockLLM(json_response={"x": 7})
    result = llm.extract_json("prompt", _S)
    assert result == {"x": 7}
    assert llm.extract_json_calls[0][1] is _S


# ---------------------------------------------------------------------------
# build_llm factory
# ---------------------------------------------------------------------------


def test_build_llm_returns_ollama_by_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    llm = build_llm("ollama", "llama3.1")
    assert isinstance(llm, OllamaLLM)
    assert llm.model == "llama3.1"
    assert llm.base_url == "http://localhost:11434"


def test_build_llm_ollama_respects_env_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434")
    llm = build_llm("ollama", "llama3.1")
    assert isinstance(llm, OllamaLLM)
    assert llm.base_url == "http://gpu-box:11434"


def test_build_llm_ollama_accepts_explicit_base_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    llm = build_llm("ollama", "m", base_url="http://custom:11434")
    assert isinstance(llm, OllamaLLM)
    assert llm.base_url == "http://custom:11434"


def test_build_llm_uses_provider_default_model():
    llm = build_llm("ollama")
    assert isinstance(llm, OllamaLLM)
    assert llm.model == "lfm2.5-thinking"


def test_build_llm_anthropic_requires_sdk(monkeypatch):
    monkeypatch.setattr(llm_module, "_ANTHROPIC_AVAILABLE", False)
    with pytest.raises(ImportError, match="anthropic package not installed"):
        build_llm("anthropic", "claude-sonnet-4-6")


def test_build_llm_openai_requires_sdk(monkeypatch):
    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", False)
    with pytest.raises(ImportError, match="openai package not installed"):
        build_llm("openai", "gpt-4o")


def test_build_llm_gemini_requires_sdk(monkeypatch):
    monkeypatch.setattr(llm_module, "_GEMINI_AVAILABLE", False)
    with pytest.raises(ImportError, match="google-genai package not installed"):
        build_llm("gemini", "gemini-2.0-flash")


def test_build_llm_openrouter_requires_openai_sdk(monkeypatch):
    monkeypatch.setattr(llm_module, "_OPENAI_AVAILABLE", False)
    with pytest.raises(ImportError, match="openai package not installed"):
        build_llm("openrouter", "anthropic/claude-sonnet-4-6")


def test_build_llm_unknown_provider_raises_value_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_llm("cohere", "command-r")


def test_build_llm_passes_temperature_to_ollama(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    llm = build_llm("ollama", "m", temperature=0.8)
    assert isinstance(llm, OllamaLLM)
    assert llm.temperature == 0.8
