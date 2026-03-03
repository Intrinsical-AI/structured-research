"""Unit tests for infra.llm ChatOllama adapter behavior."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from structured_search.infra import llm as llm_module


def test_ollama_generate_uses_chat_content_string(monkeypatch):
    class _FakeChat:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _prompt):
            return type("_Msg", (), {"content": "hello from chat"})()

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_LangChainChatOllama", _FakeChat, raising=False)

    llm = llm_module.OllamaLLM(model="llama3.1")
    assert llm.generate("ping") == "hello from chat"


def test_ollama_generate_coerces_list_content(monkeypatch):
    class _FakeChat:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _prompt):
            return type(
                "_Msg",
                (),
                {"content": [{"text": "hello "}, {"text": "world"}, "!"]},
            )()

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_LangChainChatOllama", _FakeChat, raising=False)

    llm = llm_module.OllamaLLM(model="llama3.1")
    assert llm.generate("ping") == "hello world!"


def test_ollama_generate_runtime_error_wrap(monkeypatch):
    class _FakeChat:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _prompt):
            raise RuntimeError("upstream failure")

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_LangChainChatOllama", _FakeChat, raising=False)

    llm = llm_module.OllamaLLM(model="llama3.1")
    with pytest.raises(RuntimeError, match="Ollama generation failed"):
        llm.generate("ping")


def test_ollama_generate_uses_http_fallback_without_langchain(monkeypatch):
    class _FakeResponse:
        def __init__(self, payload: str):
            self._payload = payload

        def read(self):
            return self._payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    captured: dict[str, str | None] = {"url": None, "body": None}

    def _fake_urlopen(request, timeout=60):
        _ = timeout
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse('{"message":{"content":"hello http"}}')

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", False)
    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _fake_urlopen)

    llm = llm_module.OllamaLLM(model="llama3.1", base_url="http://localhost:11434")
    assert llm.generate("ping") == "hello http"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert '"model": "llama3.1"' in (captured["body"] or "")
    assert '"content": "ping"' in (captured["body"] or "")


def test_ollama_generate_http_fallback_model_not_found_hint(monkeypatch):
    def _fake_urlopen(_request, timeout=60):
        _ = timeout
        raise RuntimeError("model 'foo' not found")

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", False)
    monkeypatch.setattr(llm_module.urllib_request, "urlopen", _fake_urlopen)

    llm = llm_module.OllamaLLM(model="foo")
    with pytest.raises(RuntimeError, match=r"hint: run `ollama pull foo`"):
        llm.generate("ping")


def test_ollama_extract_json_uses_with_structured_output(monkeypatch):
    class _Output(BaseModel):
        summary: str
        highlights: list[str]
        cited_claim_ids: list[str]

    class _Structured:
        def invoke(self, _prompt):
            return _Output(
                summary="ok",
                highlights=["h1"],
                cited_claim_ids=["C-1"],
            )

    class _FakeChat:
        def __init__(self, **_kwargs):
            pass

        def with_structured_output(self, schema):
            assert schema is _Output
            return _Structured()

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_LangChainChatOllama", _FakeChat, raising=False)

    llm = llm_module.OllamaLLM(model="llama3.1")
    data = llm.extract_json("prompt", _Output)
    assert data["summary"] == "ok"
    assert data["highlights"] == ["h1"]
    assert data["cited_claim_ids"] == ["C-1"]


def test_ollama_extract_json_falls_back_when_structured_output_fails(monkeypatch):
    class _Output(BaseModel):
        summary: str
        highlights: list[str]
        cited_claim_ids: list[str]

    class _FakeChat:
        def __init__(self, **_kwargs):
            pass

        def with_structured_output(self, _schema):
            raise RuntimeError("structured path failed")

        def invoke(self, _prompt):
            return type(
                "_Msg",
                (),
                {"content": ('{"summary":"raw","highlights":["h1"],"cited_claim_ids":["C-1"]}')},
            )()

    monkeypatch.setattr(llm_module, "_LANGCHAIN_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "_LangChainChatOllama", _FakeChat, raising=False)

    llm = llm_module.OllamaLLM(model="llama3.1")
    data = llm.extract_json("prompt", _Output)
    assert data["summary"] == "raw"
