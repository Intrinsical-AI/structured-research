"""Tests for root-level vuln_triage glue scripts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def _load_script_module(repo_root: Path, name: str):
    script_path = repo_root.parent / "synergy" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_record(**overrides):
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
        "severity": "HIGH",
        "published_at": "2012-02-01T00:00:00Z",
        "updated_at": "2012-02-02T00:00:00Z",
        "vuln_code": "def aesEncrypt(data, key): return cipher.encrypt(data)",
        "fixed_code": "def aesEncrypt(data, key): return cipher.process(data)",
        "trainable": True,
        "quality": {"parse_ok": True},
    }
    record.update(overrides)
    return record


def test_vulns_batch_triage_writes_scored_output(tmp_path: Path, repo_root: Path):
    module = _load_script_module(repo_root, "vulns_batch_triage")
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "scored.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(_sample_record()),
                json.dumps(
                    _sample_record(id="demo-low", language="go", score=3.1, severity="LOW")
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = module.run_batch_triage(
        input_path=input_path,
        output_path=output_path,
        profile_id="high_severity_python",
        structured_research_root=repo_root,
        runs_dir=tmp_path / "runs",
        allow_invalid=False,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert result["gate_passed"] == 1
    assert result["gate_failed"] == 1
    assert len(lines) == 2


def test_vulns_ingest_rag_writes_canonical_payload(tmp_path: Path, repo_root: Path):
    module = _load_script_module(repo_root, "vulns_ingest_rag")
    input_path = tmp_path / "input.jsonl"
    payload_path = tmp_path / "payload.json"
    input_path.write_text(json.dumps(_sample_record()), encoding="utf-8")

    exit_code = module.main(
        [
            "--input",
            str(input_path),
            "--payload-out",
            str(payload_path),
            "--no-import",
        ]
    )

    assert exit_code == 0
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["replace_scope"] is True
    assert payload["scope"] == "vuln-triage:input"
    assert payload["documents"][0]["external_id"] == "vuln:PYSEC-2012-1_91becae"
    assert payload["documents"][0]["metadata"]["record_type"] == "vuln_record"
    assert payload["documents"][0]["metadata"]["commit_fix"] == (
        "91becae76101cf87ce8cbfabe3af2622fc328fe5"
    )


def test_vulns_ingest_rag_import_uses_json_flag(tmp_path: Path, repo_root: Path, monkeypatch):
    module = _load_script_module(repo_root, "vulns_ingest_rag")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"scope": "demo", "snapshot_id": "s1", "documents": []}))

    calls: list[list[str]] = []

    def _fake_run(cmd, cwd, env, check):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    module.import_payloads([payload_path], repo_root.parent / "rag-prototype")

    assert calls == [["uv", "run", "rag-import-canonical", "--json", str(payload_path)]]


def test_vuln_pilot_profiles_produce_different_gate_counts(tmp_path: Path, repo_root: Path):
    module = _load_script_module(repo_root, "vulns_batch_triage")
    input_path = repo_root.parent / "synergy" / "vuln_pilot" / "prepared" / "pilot_small_v1.jsonl"

    high_path = tmp_path / "high.jsonl"
    cwe78_path = tmp_path / "cwe78.jsonl"

    high_result = module.run_batch_triage(
        input_path=input_path,
        output_path=high_path,
        profile_id="high_severity_python",
        structured_research_root=repo_root,
        runs_dir=tmp_path / "runs-high",
        allow_invalid=False,
    )
    cwe78_result = module.run_batch_triage(
        input_path=input_path,
        output_path=cwe78_path,
        profile_id="cwe_78_focus",
        structured_research_root=repo_root,
        runs_dir=tmp_path / "runs-cwe78",
        allow_invalid=False,
    )

    assert high_result["gate_passed"] > 0
    assert cwe78_result["gate_passed"] > 0
    assert high_result["gate_passed"] != cwe78_result["gate_passed"]

    cwe78_records = [
        json.loads(line)
        for line in cwe78_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        record.get("gate_passed") and record.get("cwe_id") == "CWE-78" for record in cwe78_records
    )
