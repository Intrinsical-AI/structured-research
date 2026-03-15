"""Unit tests for vuln_triage models, registry wiring, and scoring."""

from __future__ import annotations

from structured_search.application.core.ingest_service import ingest_validate_jsonl
from structured_search.application.core.run_service import run_score
from structured_search.application.core.task_registry import get_task_registry
from structured_search.contracts import RunScoreRequest
from structured_search.domain.vuln_triage.models import VulnRecord
from structured_search.infra.vuln_triage_scoring import VulnTriageScorer


def _sample_vuln_record(**overrides):
    record = {
        "id": "PYSEC-2012-1_91becae",
        "source": "dataset_raw",
        "repo": "bbangert/beaker",
        "repo_url": "https://github.com/bbangert/beaker",
        "language": "Python",
        "file_path": "beaker/crypto.py",
        "commit_fixed": "91becae76101cf87ce8cbfabe3af2622fc328fe5",
        "commit_vuln": None,
        "cve_id": None,
        "cwe_id": "CWE-327",
        "summary": "Weak cryptography in aesEncrypt",
        "score": 7.5,
        "severity": "high",
        "published_at": "2012-02-01T00:00:00Z",
        "updated_at": "2012-02-02T00:00:00Z",
        "vuln_code": "def aesEncrypt(data, key): return cipher.encrypt(data)",
        "fixed_code": "def aesEncrypt(data, key): return cipher.process(data)",
        "trainable": True,
        "quality": {"parse_ok": True},
    }
    record.update(overrides)
    return record


def test_vuln_record_maps_fce_fields():
    record = VulnRecord.model_validate(_sample_vuln_record())
    assert record.language == "python"
    assert record.severity == "HIGH"
    assert record.cvss_score == 7.5
    assert record.commit_fix == "91becae76101cf87ce8cbfabe3af2622fc328fe5"
    assert record.commit_fix_url == (
        "https://github.com/bbangert/beaker/commit/91becae76101cf87ce8cbfabe3af2622fc328fe5"
    )
    assert record.osv_id == "PYSEC-2012-1"
    assert record.has_code_pair is True


def test_vuln_triage_task_registered():
    plugin = get_task_registry().get("vuln_triage")
    assert plugin.task_id == "vuln_triage"
    assert plugin.supports("jsonl_validate")
    assert plugin.supports("run")
    assert not plugin.supports("prompt")
    assert plugin.task_runtime_model is not None


def test_vuln_triage_build_runtime_uses_clean_task_specific_scorer():
    plugin = get_task_registry().get("vuln_triage")
    assert plugin.build_runtime is not None
    constraints, scorer = plugin.build_runtime(
        {
            "domain": "vuln_triage",
            "must": [],
            "prefer": [],
            "avoid": [],
        },
        {
            "gates": {
                "hard_filters_mode": "require_all",
                "hard_filters": [],
                "reject_anomalies": [],
                "required_evidence_fields": [],
            },
            "soft_scoring": {
                "formula_version": "v2_soft_after_gates",
                "prefer_weight_default": 1.0,
                "avoid_penalty_default": 1.0,
                "signal_boost": {"evidence_present": 0.0},
                "penalties": {
                    "incomplete": 1.0,
                    "inference_used": 0.2,
                    "prompt_injection_suspected": 2.0,
                },
            },
        },
    )
    assert constraints.domain == "vuln_triage"
    assert isinstance(scorer, VulnTriageScorer)


def test_vuln_triage_ingest_reports_schema_errors():
    plugin = get_task_registry().get("vuln_triage")
    result = ingest_validate_jsonl(
        raw_text='{"source":"dataset_raw"}',
        record_model=plugin.record_model,
    )
    assert result.stats.schema_errors == 1
    assert "id" in result.invalid[0].message


def test_vuln_triage_run_score_uses_default_profile_bundle():
    plugin = get_task_registry().get("vuln_triage")
    passing = _sample_vuln_record(id="PYSEC-2012-1_good", cwe_id="CWE-78")
    failing = _sample_vuln_record(
        id="GHSA-demo-low",
        language="go",
        score=4.0,
        severity="low",
        trainable=False,
        fixed_code=None,
    )
    summary = run_score(
        task_id="vuln_triage",
        request=RunScoreRequest(
            profile_id="high_severity_python",
            records=[passing, failing],
            require_snapshot=False,
        ),
        plugin=plugin,
    )
    assert summary.gate_passed == 1
    assert summary.gate_failed == 1
    assert summary.records[0]["gate_passed"] is True
    assert summary.records[1]["gate_passed"] is False
