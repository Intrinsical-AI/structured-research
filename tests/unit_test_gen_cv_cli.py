"""Unit tests for unified task action CLI (gen_cv)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import structured_search.cli as cli


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self, mode: str = "json") -> dict:
        _ = mode
        return self._payload


def test_task_action_gen_cv_invokes_handler_with_payload(tmp_path: Path, monkeypatch, capsys):
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "profile_id": "profile_example",
                "job": {"id": "job-1", "title": "Engineer", "company": "Acme", "stack": []},
                "candidate_profile": {"id": "cand-1", "seniority": "senior"},
                "allow_mock_fallback": True,
            }
        ),
        encoding="utf-8",
    )

    captured: dict = {}

    def _handler(**kwargs):
        captured.update(kwargs)
        return _Response({"ok": True, "model_info": {"fallback_used": True}})

    class _FakePlugin:
        action_handlers: ClassVar[dict[str, object]] = {"gen-cv": _handler}

        @staticmethod
        def supports(capability: str) -> bool:
            return capability == "action:gen-cv"

    monkeypatch.setattr(cli, "_plugin_or_exit", lambda _task_id: _FakePlugin())
    exit_code = cli.main(
        [
            "task",
            "gen_cv",
            "action",
            "--name",
            "gen-cv",
            "--request",
            str(request_path),
        ]
    )

    assert exit_code == 0
    assert captured["profile_id"] == "profile_example"
    assert captured["allow_mock_fallback"] is True
    stdout = capsys.readouterr().out
    assert '"ok": true' in stdout


def test_task_action_rejects_unsupported_capability(tmp_path: Path, monkeypatch):
    request_path = tmp_path / "request.json"
    request_path.write_text("{}", encoding="utf-8")

    class _FakePlugin:
        action_handlers: ClassVar[dict[str, object]] = {}

        @staticmethod
        def supports(_capability: str) -> bool:
            return False

    monkeypatch.setattr(cli, "_plugin_or_exit", lambda _task_id: _FakePlugin())
    exit_code = cli.main(
        [
            "task",
            "gen_cv",
            "action",
            "--name",
            "gen-cv",
            "--request",
            str(request_path),
        ]
    )

    assert exit_code == 1
