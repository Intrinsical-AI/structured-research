"""Unit tests for services."""

from datetime import datetime

import pytest

from structured_search.infra.exporting import MockExporter
from structured_search.infra.loading import MockLoader
from structured_search.infra.scoring import MockScorer
from structured_search.tasks.job_search.models import JobSearchConstraints
from structured_search.tasks.job_search.service import ETLJobSearch


def _valid_job_record(**overrides):
    record = {
        "id": "job_001",
        "source": "linkedin",
        "company": "Acme",
        "title": "Engineer",
        "posted_at": datetime.now().isoformat(),
        "apply_url": "https://example.com",
        "geo": {"region": "Spain", "city": "Madrid"},
        "modality": "hybrid",
        "seniority": {"level": "senior"},
    }
    record.update(overrides)
    return record


class TestETLJobSearch:
    def test_etl_process_applies_gates(self):
        etl = ETLJobSearch(
            loader=MockLoader([]),
            scorer=MockScorer(return_value=7.5, return_gate_passed=True),
            exporter=MockExporter(),
            constraints=JobSearchConstraints(domain="job_search"),
        )
        results, skipped = etl.process_phase([_valid_job_record()])
        assert len(results) == 1
        assert skipped == 0
        assert results[0].gate_passed is True
        assert results[0].score == 7.5

    def test_etl_skips_invalid_records(self):
        etl = ETLJobSearch(
            loader=MockLoader([]),
            scorer=MockScorer(return_value=5.0, return_gate_passed=False),
            exporter=MockExporter(),
            constraints=JobSearchConstraints(domain="job_search"),
        )
        # Invalid record (missing required fields) → skipped with warning
        results, skipped = etl.process_phase([{"id": "bad"}])
        assert len(results) == 0
        assert skipped == 1

    def test_etl_run_returns_full_stats(self):
        """run() must report loaded, processed, skipped and output."""
        loader = MockLoader([_valid_job_record(), {"id": "bad_record"}])
        exporter = MockExporter()
        etl = ETLJobSearch(
            loader=loader,
            scorer=MockScorer(return_value=8.0, return_gate_passed=True),
            exporter=exporter,
            constraints=JobSearchConstraints(domain="job_search"),
        )
        result = etl.run("dummy_input.jsonl", "dummy_output.jsonl")
        assert result["loaded"] == 2
        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert "output" in result
        assert "errors" in result
        assert len(result["errors"]) == 1
        assert result["errors"][0]["line_no"] == 2
        assert result["errors"][0]["kind"] == "validation_error"

    def test_etl_exports_results(self):
        exporter = MockExporter()
        etl = ETLJobSearch(
            loader=MockLoader([]),
            scorer=MockScorer(return_value=6.0, return_gate_passed=True),
            exporter=exporter,
            constraints=JobSearchConstraints(domain="job_search"),
        )
        etl.run("dummy_input.jsonl", "dummy_output.jsonl")
        # exporter.export is called (with empty results from MockLoader)
        assert exporter.records == []

    def test_etl_process_collects_structured_errors(self):
        etl = ETLJobSearch(
            loader=MockLoader([]),
            scorer=MockScorer(return_value=5.0, return_gate_passed=True),
            exporter=MockExporter(),
            constraints=JobSearchConstraints(domain="job_search"),
        )
        _, skipped = etl.process_phase([{"id": "bad"}])
        assert skipped == 1
        assert len(etl.last_errors) == 1
        assert etl.last_errors[0].line_no == 1
        assert etl.last_errors[0].kind == "validation_error"

    def test_etl_unexpected_errors_are_not_swallowed(self):
        class _ExplodingScorer:
            def score(self, _record, _constraints):
                raise KeyError("unexpected")

        etl = ETLJobSearch(
            loader=MockLoader([]),
            scorer=_ExplodingScorer(),
            exporter=MockExporter(),
            constraints=JobSearchConstraints(domain="job_search"),
        )

        with pytest.raises(KeyError):
            etl.process_phase([_valid_job_record()])


class TestMockAdapters:
    def test_mock_scorer(self):
        from structured_search.domain import BaseResult

        scorer = MockScorer(return_value=8.5, return_gate_passed=True)
        result = scorer.score(
            BaseResult(id="test_001", source="test"),
            JobSearchConstraints(domain="job_search"),
        )
        assert result.score == 8.5
        assert result.gate_passed is True

    def test_mock_loader(self):
        loader = MockLoader([{"id": "1"}, {"id": "2"}])
        assert len(loader.load("dummy")) == 2

    def test_mock_exporter(self):
        from structured_search.domain import BaseResult

        exporter = MockExporter()
        records = [
            BaseResult(id="r1", source="test"),
            BaseResult(id="r2", source="test"),
        ]
        exporter.export(records, "dummy")
        assert len(exporter.records) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
