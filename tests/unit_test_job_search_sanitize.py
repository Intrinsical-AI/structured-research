"""Unit tests for job-search input sanitization before ETL run."""

from __future__ import annotations

import json

from structured_search.tasks.job_search.models import JobPosting
from structured_search.tasks.job_search.sanitize import sanitize_jsonl_for_run


def _minimal_posting() -> dict:
    return {
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


def test_sanitize_jsonl_is_idempotent_for_clean_input(tmp_path):
    input_file = tmp_path / "input.jsonl"
    input_file.write_text(json.dumps(_minimal_posting()) + "\n", encoding="utf-8")

    summary = sanitize_jsonl_for_run(input_file)

    assert summary.used_temp_file is False
    assert summary.output_path == input_file
    assert summary.fixed_fields == 0
    assert summary.touched_records == 0
    assert input_file.read_text(encoding="utf-8") == json.dumps(_minimal_posting()) + "\n"


def test_sanitize_jsonl_fixes_markdown_links_and_nulls_and_preserves_bad_lines(tmp_path):
    record = _minimal_posting()
    record["source"] = "[https://jobs.example.com](https://jobs.example.com)"
    record["apply_url"] = "[https://acme.example.com/apply](https://acme.example.com/apply)"
    record["stack"] = None
    record["evidence"][0]["url"] = (
        "[https://acme.example.com/apply](https://acme.example.com/apply)"
    )
    record["evidence"][0]["locator"] = {"type": "text_fragment", "value\n": "x"}
    record["facts"][0] = {"field": "title", "value\n": "Engineer", "evidence_ids": ["e1"]}

    input_file = tmp_path / "input.jsonl"
    input_file.write_text(json.dumps(record) + "\nNOT_JSON\n", encoding="utf-8")

    summary = sanitize_jsonl_for_run(input_file)
    assert summary.used_temp_file is True
    assert summary.parse_errors == 1
    assert summary.touched_records == 1
    assert summary.fixed_fields >= 5

    out_lines = summary.output_path.read_text(encoding="utf-8").splitlines()
    assert out_lines[1] == "NOT_JSON"
    cleaned = json.loads(out_lines[0])

    assert cleaned["source"] == "https://jobs.example.com"
    assert cleaned["apply_url"] == "https://acme.example.com/apply"
    assert cleaned["stack"] == []
    assert cleaned["evidence"][0]["url"] == "https://acme.example.com/apply"
    assert cleaned["evidence"][0]["locator"]["value"] == "x"
    assert cleaned["facts"][0]["value"] == "Engineer"
    JobPosting.model_validate(cleaned)

    second_pass = sanitize_jsonl_for_run(summary.output_path)
    assert second_pass.used_temp_file is False
    assert second_pass.fixed_fields == 0

    summary.output_path.unlink(missing_ok=True)
