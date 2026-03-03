"""Regression tests for helper command modules under structured_search.tools."""

from __future__ import annotations

import json

from structured_search.tools import (
    extract_p2_postings,
    populate_jsonl_validate_metrics,
    report_q2_metrics,
    validate_atoms,
    validate_results,
)


def test_validate_atoms_discovers_nested_files(tmp_path):
    atoms_dir = tmp_path / "atoms"
    (atoms_dir / "context").mkdir(parents=True)
    (atoms_dir / "claims" / "nested").mkdir(parents=True)
    (atoms_dir / "evidence" / "deep").mkdir(parents=True)

    (atoms_dir / "context" / "ctx.yaml").write_text("id: c1\ntype: context\n")
    (atoms_dir / "claims" / "nested" / "clm.yaml").write_text("id: cl1\ntype: claim\n")
    (atoms_dir / "evidence" / "deep" / "ev.yaml").write_text("id: e1\ntype: evidence\n")

    discovered = validate_atoms.discover_atom_files(atoms_dir)
    rel = {p.relative_to(atoms_dir).as_posix() for p in discovered}

    assert "context/ctx.yaml" in rel
    assert "claims/nested/clm.yaml" in rel
    assert "evidence/deep/ev.yaml" in rel
    assert len(discovered) == 3


def test_extract_p2_clean_url_parses_markdown_links():
    assert (
        extract_p2_postings.clean_url("[https://example.com/jobs/1](https://example.com/jobs/1)")
        == "https://example.com/jobs/1"
    )
    assert (
        extract_p2_postings.clean_url("[https://example.com/jobs/2")
        == "https://example.com/jobs/2"
    )


def test_validate_results_overwrites_previous_output(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()

    valid_record = {"id": "job-1", "title": "Engineer", "company": "Acme"}
    invalid_record = {"id": "missing-fields"}
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(x) for x in (valid_record, invalid_record)),
        encoding="utf-8",
    )

    first = validate_results.validate_results(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        task="gen_cv",
        strict=False,
    )
    assert first == 0
    results_file = output_dir / "results.jsonl"
    assert results_file.exists()
    assert len(results_file.read_text(encoding="utf-8").splitlines()) == 1

    # Re-run with same input; output should be rewritten, not appended.
    second = validate_results.validate_results(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        task="gen_cv",
        strict=False,
    )
    assert second == 0
    assert len(results_file.read_text(encoding="utf-8").splitlines()) == 1


def test_report_q2_metrics_computes_expected_ratios():
    events = [
        {"event_type": "job_search_run", "latency_ms": 1000, "snapshot_status": "written"},
        {"event_type": "job_search_run", "latency_ms": 2000, "snapshot_status": "failed"},
        {"event_type": "job_search_jsonl_validate", "total_lines": 10, "parse_errors": 2},
        {"event_type": "gen_cv", "fallback_used": True},
        {"event_type": "gen_cv", "fallback_used": False},
    ]

    report = report_q2_metrics.compute_report(events)
    metrics = report["metrics"]

    assert metrics["run_latency_p95_ms"] is not None
    assert metrics["snapshot_failed_rate"] == 0.5
    assert metrics["jsonl_parse_error_ratio"] == 0.2
    assert metrics["gen_cv_fallback_used_ratio"] == 0.5


def test_populate_jsonl_validate_metrics_helpers(tmp_path):
    assert (
        populate_jsonl_validate_metrics.normalize_api_base("http://127.0.0.1:8000")
        == "http://127.0.0.1:8000/v1"
    )
    assert (
        populate_jsonl_validate_metrics.normalize_api_base("http://127.0.0.1:8000/v1/")
        == "http://127.0.0.1:8000/v1"
    )

    file_a = tmp_path / "a.jsonl"
    file_b = tmp_path / "b.jsonl"
    file_a.write_text("{}", encoding="utf-8")
    file_b.write_text("{}", encoding="utf-8")

    collected = populate_jsonl_validate_metrics.collect_input_files(
        [str(file_a), str(file_b)],
        glob_pattern="unused/*.jsonl",
        max_files=1,
    )
    assert collected == [file_a]
