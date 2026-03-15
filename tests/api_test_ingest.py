"""Tests for JSONL ingest/validate: TolerantJSONLParser + application ingest use-case."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from structured_search.api.wiring import JOB_SEARCH_PLUGIN_WIRED as _PLUGIN
from structured_search.application.core.ingest_service import ingest_validate_jsonl
from structured_search.infra.loading import TolerantJSONLParser

_MINIMAL_POSTING = {
    "id": "test-001",
    "source": "test",
    "company": "Acme",
    "title": "Engineer",
    "posted_at": "2026-01-15",
    "apply_url": "https://acme.example.com/apply",
    "geo": {"region": "ES-MD", "city": "Madrid", "country": "Spain"},
    "modality": "remote",
    "seniority": {"level": "senior"},
    "stack": ["Python"],
    "evidence": [
        {
            "id": "e1",
            "field": "title",
            "quote": "Senior Engineer",
            "url": "https://acme.example.com/apply",
            "retrieved_at": "2026-01-15T10:00:00",
            "locator": {"type": "text_fragment", "value": "Senior Engineer"},
            "source_kind": "html",
        }
    ],
    "facts": [{"field": "title", "value": "Engineer", "evidence_ids": ["e1"]}],
    "inferences": [],
    "anomalies": [],
    "incomplete": False,
}


def _jsonl(*dicts) -> str:
    return "\n".join(json.dumps(d) for d in dicts)


class TestTolerantJSONLParser:
    def _parser(self) -> TolerantJSONLParser:
        return TolerantJSONLParser()

    def test_single_valid_line(self):
        parser = self._parser()
        valid, errors = parser.parse('{"a": 1}')
        assert valid == [{"a": 1}]
        assert errors == []

    def test_invalid_json_collected_not_raised(self):
        parser = self._parser()
        text = '{"a": 1}\nNOT JSON\n{"b": 2}'
        valid, errors = parser.parse(text)
        assert len(valid) == 2
        assert len(errors) == 1
        assert errors[0].kind == "json_parse"
        assert errors[0].line_no == 2

    def test_multiline_json_object(self):
        parser = self._parser()
        text = textwrap.dedent(
            """\
            {
              "a": 1,
              "b": "hello"
            }
        """
        )
        valid, errors = parser.parse(text)
        assert valid == [{"a": 1, "b": "hello"}]
        assert errors == []

    def test_bare_open_brace_does_not_swallow_following_records(self):
        parser = self._parser()
        text = textwrap.dedent(
            """\
            {"a": 1}
            {
            {"b": 2}
            {"c": 3}
            """
        )
        valid, errors = parser.parse(text)
        assert valid == [{"a": 1}, {"b": 2}, {"c": 3}]
        assert len(errors) == 1
        assert errors[0].kind == "json_parse"
        assert errors[0].line_no == 2


class TestIngestValidateJsonl:
    def test_clean_valid_record(self):
        assert _PLUGIN.record_model is not None
        result = ingest_validate_jsonl(
            raw_text=json.dumps(_MINIMAL_POSTING),
            record_model=_PLUGIN.record_model,
        )
        assert result.stats.schema_ok == 1
        assert result.stats.schema_errors == 0

    def test_valid_and_schema_invalid_mix(self):
        bad = {"id": "bad-001", "source": "x"}
        assert _PLUGIN.record_model is not None
        result = ingest_validate_jsonl(
            raw_text=_jsonl(_MINIMAL_POSTING, bad),
            record_model=_PLUGIN.record_model,
        )
        assert result.stats.schema_ok == 1
        assert result.stats.schema_errors == 1

    def test_broken_json_line_counted(self):
        assert _PLUGIN.record_model is not None
        result = ingest_validate_jsonl(
            raw_text=f"{json.dumps(_MINIMAL_POSTING)}\nNOT_JSON",
            record_model=_PLUGIN.record_model,
        )
        assert result.stats.parse_errors == 1
        assert result.stats.schema_ok == 1

    def test_inference_string_returns_actionable_schema_message(self):
        bad = dict(_MINIMAL_POSTING)
        bad["inferences"] = ["salary_inferred"]
        assert _PLUGIN.record_model is not None
        result = ingest_validate_jsonl(
            raw_text=json.dumps(bad),
            record_model=_PLUGIN.record_model,
        )
        assert result.stats.schema_errors == 1
        assert any(
            "inferences[0] must be an object with keys" in err.message for err in result.invalid
        )


_RESULTS_DIR = Path(__file__).parent.parent / "results" / "job_search"


def _find_result_files() -> list[Path]:
    if not _RESULTS_DIR.exists():
        return []
    return list(_RESULTS_DIR.rglob("results.jsonl"))


@pytest.mark.integration
@pytest.mark.parametrize(
    "results_file", _find_result_files(), ids=lambda p: str(p.relative_to(_RESULTS_DIR))
)
def test_real_results_jsonl(results_file: Path):
    raw_text = results_file.read_text(encoding="utf-8")
    assert _PLUGIN.record_model is not None
    result = ingest_validate_jsonl(raw_text=raw_text, record_model=_PLUGIN.record_model)

    total = result.stats.total_lines
    if total == 0:
        pytest.skip(f"Empty results file: {results_file}")

    if result.stats.parse_errors > 0:
        sample = result.invalid[0]
        print(
            f"\n[{results_file.name}] {result.stats.parse_errors} parse errors, "
            f"first: line={sample.line_no} kind={sample.kind} msg={sample.message[:80]}"
        )

    if result.stats.schema_errors > 0:
        schema_errs = [e for e in result.invalid if e.kind == "schema_validation"]
        print(
            f"[{results_file.name}] {len(schema_errs)} schema errors, "
            f"first: {schema_errs[0].message[:120]}"
        )
