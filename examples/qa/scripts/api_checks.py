#!/usr/bin/env python3
"""QA API Contract Checks — structured-research.

Tests all HTTP endpoints against the contract defined in docs/API_CONTRACT_V1.md.
Requires a running API (default: http://localhost:8000).

Usage:
    python3 examples/qa/scripts/api_checks.py
    python3 examples/qa/scripts/api_checks.py --api-base http://localhost:8000
    python3 examples/qa/scripts/api_checks.py --test T01.3
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]  # repo root
QA_DATA = ROOT / "examples" / "qa" / "data"
EXAMPLE_PAYLOADS = ROOT / "examples" / "job_search" / "profile_example"
CONFIG_PROFILES = ROOT / "config" / "job_search" / "profile_example"


# ── Mini test harness ────────────────────────────────────────────────────────
_pass = 0
_fail = 0
_only_test: str | None = None


def check(label: str, condition: bool, detail: str = "") -> bool:
    global _pass, _fail
    if _only_test and not label.startswith(_only_test):
        return True
    if condition:
        print(f"  PASS {label}")
        _pass += 1
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        _fail += 1
    return condition


def http(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    """Make an HTTP request and return (status_code, response_body)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body_bytes = exc.read()
            return exc.code, json.loads(body_bytes)
        except Exception:
            return exc.code, {}
    except urllib.error.URLError as exc:
        print(f"\nERROR: Cannot reach API at {url}")
        print(f"       {exc.reason}")
        print("       Start the API with: uv run structured-search dev api --reload")
        sys.exit(2)


def jsonl_to_string(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def jsonl_to_records(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Tests ────────────────────────────────────────────────────────────────────


def run_t01(base: str) -> None:
    print("\n── T01: Happy Path ──")

    # T01.1 GET /v1/tasks/job_search/profiles
    status, body = http("GET", f"{base}/v1/tasks/job_search/profiles")
    check("T01.1 GET /profiles → 200", status == 200, f"got {status}")
    ids: list[str] = (
        [p["id"] for p in body if isinstance(p, dict) and isinstance(p.get("id"), str)]
        if isinstance(body, list)
        else []
    )
    check("T01.1 profile_example present", "profile_example" in ids, f"got {ids}")

    # T01.2 GET /v1/tasks/job_search/profiles/profile_example/bundle
    status, body = http("GET", f"{base}/v1/tasks/job_search/profiles/profile_example/bundle")
    check("T01.2 GET /bundle → 200", status == 200, f"got {status}")
    check("T01.2 bundle has constraints", "constraints" in body, str(body)[:100])

    # T01.3 POST /v1/tasks/job_search/prompt/generate
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/prompt/generate",
        {"profile_id": "profile_example", "step": "S3_execute"},
    )
    check("T01.3 POST /prompt/generate → 200", status == 200, f"got {status}")
    check(
        "T01.3 prompt_hash starts with sha256:",
        (body.get("prompt_hash") or "").startswith("sha256:"),
    )
    check("T01.3 constraints_embedded=true", body.get("constraints_embedded") is True)

    # T01.4 POST /v1/tasks/job_search/jsonl/validate — valid batch
    raw_jsonl = jsonl_to_string(QA_DATA / "valid_batch.jsonl")
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/jsonl/validate",
        {"raw_jsonl": raw_jsonl, "profile_id": "profile_example"},
    )
    check("T01.4 POST /jsonl/validate → 200", status == 200, f"got {status}")
    metrics = body.get("metrics", {})
    check(
        "T01.4 5 valid records",
        metrics.get("schema_valid_records") == 5,
        f"got {metrics.get('schema_valid_records')}",
    )
    check(
        "T01.4 0 invalid lines",
        metrics.get("invalid_lines") == 0,
        f"got {metrics.get('invalid_lines')}",
    )

    # T01.5 POST /v1/tasks/job_search/run/validate
    valid_records = jsonl_to_records(QA_DATA / "valid_batch.jsonl")
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/run/validate",
        {"profile_id": "profile_example", "records": valid_records, "require_snapshot": False},
    )
    check("T01.5 POST /run/validate → 200", status == 200, f"got {status}")

    # T01.6 POST /v1/tasks/job_search/run
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/run",
        {"profile_id": "profile_example", "records": valid_records, "require_snapshot": False},
    )
    check("T01.6 POST /run → 200", status == 200, f"got {status}")
    records = body.get("scored_records", [])
    check("T01.6 5 scored records returned", len(records) == 5, f"got {len(records)}")
    run_metrics = body.get("metrics", {})
    check("T01.6 metrics.gate_passed=4", run_metrics.get("gate_passed") == 4, str(run_metrics))
    check("T01.6 metrics.gate_failed=1", run_metrics.get("gate_failed") == 1, str(run_metrics))
    check(
        "T01.6 metrics.gate_pass_rate=0.8",
        run_metrics.get("gate_pass_rate") == 0.8,
        str(run_metrics),
    )

    # Verify specific scores
    by_id = {r["id"]: r for r in records}
    check(
        "T01.6 QA-V01 score=9.5",
        by_id.get("QA-V01", {}).get("score") == 9.5,
        f"got {by_id.get('QA-V01', {}).get('score')}",
    )
    check("T01.6 QA-V03 gate_passed=False", by_id.get("QA-V03", {}).get("gate_passed") is False)
    check(
        "T01.6 QA-V04 score=8.0",
        by_id.get("QA-V04", {}).get("score") == 8.0,
        f"got {by_id.get('QA-V04', {}).get('score')}",
    )


def run_t02(base: str) -> None:
    print("\n── T02: Score Clamping ──")

    edge_records = jsonl_to_records(QA_DATA / "edge_cases.jsonl")

    # T02.1 Score clamp at 10.0 with qa_weighted
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/run",
        {"profile_id": "qa_weighted", "records": edge_records, "require_snapshot": False},
    )
    check("T02.1 qa_weighted run → 200", status == 200, f"got {status}")
    by_id = {r["id"]: r for r in body.get("scored_records", [])}
    e01 = by_id.get("QA-E01", {})
    check("T02.1 QA-E01 score=10.0", e01.get("score") == 10.0, f"got {e01.get('score')}")
    raw = (e01.get("score_breakdown") or {}).get("raw_score", 0)
    check("T02.1 QA-E01 raw_score>10", raw > 10, f"got raw={raw}")

    # T02.2 Score clamp at 0.0 with qa_open
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/run",
        {"profile_id": "qa_open", "records": edge_records, "require_snapshot": False},
    )
    check("T02.2 qa_open run → 200", status == 200, f"got {status}")
    by_id = {r["id"]: r for r in body.get("scored_records", [])}
    e02 = by_id.get("QA-E02", {})
    check("T02.2 QA-E02 gate_passed=True (qa_open accepts all)", e02.get("gate_passed") is True)
    check("T02.2 QA-E02 score=0.0", e02.get("score") == 0.0, f"got {e02.get('score')}")
    raw = (e02.get("score_breakdown") or {}).get("raw_score", 0)
    check("T02.2 QA-E02 raw_score<0", raw < 0, f"got raw={raw}")


def run_t03(base: str) -> None:
    print("\n── T03: JSONL Hostility ──")

    hostile_jsonl = jsonl_to_string(QA_DATA / "hostile.jsonl")
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/jsonl/validate",
        {"raw_jsonl": hostile_jsonl, "profile_id": "profile_example"},
    )
    check("T03.1 hostile.jsonl validate → 200", status == 200, f"got {status}")

    metrics = body.get("metrics", {})
    valid_records = body.get("valid_records", [])
    invalid_records = body.get("invalid_records", [])

    # We expect exactly 4 valid records: CTRL-01, H-INJECT, H-LONGDESC, H-UNI, H-EXTRA, CTRL-02
    # (injection passes schema — only schema check, not semantic)
    valid_ids = {r.get("id") for r in valid_records}
    check("T03.2 QA-H-CTRL-01 is valid", "QA-H-CTRL-01" in valid_ids)
    check(
        "T03.3 QA-H-INJECT is valid (schema-only check, no semantic filter)",
        "QA-H-INJECT" in valid_ids,
        "FINDING: injection text in title passes schema validation",
    )
    check(
        "T03.4 QA-H-LONGDESC is valid (no field length limit)",
        "QA-H-LONGDESC" in valid_ids,
        "FINDING: no max field length enforced at ingest",
    )
    check("T03.5 QA-H-UNI is valid (unicode ok)", "QA-H-UNI" in valid_ids)
    check("T03.6 QA-H-EXTRA is valid (extra fields tolerated)", "QA-H-EXTRA" in valid_ids)

    check(
        "T03.7 some parse errors reported",
        metrics.get("invalid_lines", 0) > 0,
        "expected parse/schema errors from malformed lines",
    )
    check(
        "T03.8 QA-H-BAD-MOD is invalid",
        any("QA-H-BAD-MOD" in (r.get("raw") or "") for r in invalid_records),
        "modality='office' should fail schema",
    )
    check(
        "T03.9 QA-H-BAD-INF is invalid",
        any("QA-H-BAD-INF" in (r.get("raw") or "") for r in invalid_records),
        "inferences=[string] should fail schema (FINDING F03)",
    )


def run_t04(base: str) -> None:
    print("\n── T04: Bundle/Config Edge Cases ──")

    # T04.1 Invalid operator
    invalid_bundle = {
        "profile_id": "qa_badop",
        "constraints": {
            "domain": "job_search",
            "must": [{"field": "modality", "op": "regex", "value": "remote.*"}],
        },
        "task": {
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
            },
        },
        "task_config": {"agent_name": "QA", "version": "1.0", "language_priority": ["en"]},
        "user_profile": {"timezone": "UTC", "mobility": "remote", "currency_default": "EUR"},
    }
    status, body = http(
        "PUT", f"{base}/v1/tasks/job_search/profiles/qa_badop/bundle", invalid_bundle
    )
    check(
        "T04.1 invalid op 'regex' → rejected (not 200 ok)",
        not (status == 200 and body.get("ok") is True),
        f"status={status} ok={body.get('ok')}",
    )

    # T04.2 weighted op mismatched weights
    bad_weighted = {
        "profile_id": "qa_badweights",
        "constraints": {
            "domain": "job_search",
            "prefer": [
                {
                    "field": "stack",
                    "op": "weighted",
                    "value": ["a", "b", "c"],
                    "weights": [1.0, 2.0],
                }
            ],
        },
        "task": {
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
            },
        },
        "task_config": {"agent_name": "QA", "version": "1.0", "language_priority": ["en"]},
        "user_profile": {"timezone": "UTC", "mobility": "remote", "currency_default": "EUR"},
    }
    status, body = http(
        "PUT", f"{base}/v1/tasks/job_search/profiles/qa_badweights/bundle", bad_weighted
    )
    check(
        "T04.2 weighted op len mismatch → 200/ok=false",
        status == 200 and body.get("ok") is False,
        f"status={status} body={body}",
    )

    # T04.3 Path traversal → 404 (not file system breach)
    status, body = http("GET", f"{base}/v1/tasks/job_search/profiles/../../etc/passwd/bundle")
    check("T04.3 path traversal → 404 (not 200/500)", status == 404, f"got {status}")

    # T04.4 Profile ID override: URL takes precedence over body
    bundle = load_json(CONFIG_PROFILES / "bundle.json")
    bundle["profile_id"] = "wrong_id_in_body"
    status, body = http(
        "PUT", f"{base}/v1/tasks/job_search/profiles/qa_id_override/bundle", bundle
    )
    if status == 200 and body.get("ok"):
        _, saved = http("GET", f"{base}/v1/tasks/job_search/profiles/qa_id_override/bundle")
        check(
            "T04.4 URL profile_id overrides body",
            saved.get("profile_id") == "qa_id_override",
            f"got {saved.get('profile_id')}",
        )

    # T04.5 list op with empty value list → 422
    bad_empty = {
        "profile_id": "qa_emptylist",
        "constraints": {
            "domain": "job_search",
            "must": [{"field": "modality", "op": "in", "value": []}],
        },
        "task": {
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
            },
        },
        "task_config": {"agent_name": "QA", "version": "1.0", "language_priority": ["en"]},
        "user_profile": {"timezone": "UTC", "mobility": "remote", "currency_default": "EUR"},
    }
    status, body = http(
        "PUT", f"{base}/v1/tasks/job_search/profiles/qa_emptylist/bundle", bad_empty
    )
    check(
        "T04.5 op 'in' with empty value list → 200/ok=false",
        status == 200 and body.get("ok") is False,
        f"status={status} body={body}",
    )


def run_t05(base: str) -> None:
    print("\n── T05: API Contract ──")

    # T05.1 Wrong HTTP method
    status, _ = http("POST", f"{base}/v1/tasks/job_search/profiles")
    check("T05.1 POST /profiles → 405", status == 405, f"got {status}")

    status, _ = http("GET", f"{base}/v1/tasks/job_search/jsonl/validate")
    check("T05.2 GET /jsonl/validate → 405", status == 405, f"got {status}")

    # T05.3 Missing required field in body
    status, body = http("POST", f"{base}/v1/tasks/job_search/jsonl/validate", {})
    check("T05.3 missing raw_jsonl → 422", status == 422, f"got {status}")

    # T05.4 Non-existent profile → 404
    status, _ = http("GET", f"{base}/v1/tasks/job_search/profiles/does_not_exist_xyz/bundle")
    check("T05.4 unknown profile → 404", status == 404, f"got {status}")

    # T05.5 Empty JSONL to /run
    status, body = http(
        "POST",
        f"{base}/v1/tasks/job_search/run",
        {"profile_id": "profile_example", "records": [], "require_snapshot": False},
    )
    check("T05.5 empty JSONL → 200", status == 200, f"got {status}")
    metrics = body.get("metrics", {})
    check(
        "T05.5 empty JSONL processed=0",
        metrics.get("processed", -1) == 0,
        f"got {metrics.get('processed')}",
    )

    # T05.6 gen-cv with mock fallback (no Ollama needed)
    if (EXAMPLE_PAYLOADS / "job.json").exists() and (EXAMPLE_PAYLOADS / "candidate.json").exists():
        job = load_json(EXAMPLE_PAYLOADS / "job.json")
        candidate = load_json(EXAMPLE_PAYLOADS / "candidate.json")
        status, body = http(
            "POST",
            f"{base}/v1/tasks/gen_cv/actions/gen-cv",
            {
                "profile_id": "profile_example",
                "job": job,
                "candidate_profile": candidate,
                "allow_mock_fallback": True,
            },
        )
        check("T05.6 gen-cv mock fallback → 200", status == 200, f"got {status}")
        check("T05.6 gen-cv returns cv_markdown", bool(body.get("cv_markdown")), str(body)[:100])
        check(
            "T05.6 gen-cv fallback_used=True",
            (body.get("model_info") or {}).get("fallback_used") is True,
        )

    # T05.7 gen-cv without mock (expect 503 if no Ollama)
    if (EXAMPLE_PAYLOADS / "job.json").exists() and (EXAMPLE_PAYLOADS / "candidate.json").exists():
        job = load_json(EXAMPLE_PAYLOADS / "job.json")
        candidate = load_json(EXAMPLE_PAYLOADS / "candidate.json")
        status, body = http(
            "POST",
            f"{base}/v1/tasks/gen_cv/actions/gen-cv",
            {
                "profile_id": "profile_example",
                "job": job,
                "candidate_profile": candidate,
                "allow_mock_fallback": False,
            },
        )
        check(
            "T05.7 gen-cv no fallback + no Ollama → 503",
            status == 503,
            f"got {status} (only passes if Ollama is not running)",
        )


def run_t06(base: str) -> None:
    print("\n── T06: Legacy Field Rejection (F01) ──")

    # Legacy field is now rejected at bundle validation.
    status, bundle = http("GET", f"{base}/v1/tasks/job_search/profiles/qa_strict/bundle")
    if status != 200:
        print("  SKIP T06 — qa_strict not loaded")
        return

    bundle["profile_id"] = "qa_f01_test"
    bundle.setdefault("task", {}).setdefault("gates", {})["must_pass_constraints_must"] = False

    status, put_body = http(
        "PUT", f"{base}/v1/tasks/job_search/profiles/qa_f01_test/bundle", bundle
    )
    if status != 200:
        print(f"  SKIP T06.1 — could not save test bundle (status {status})")
        return

    issues = put_body.get("errors", [])
    has_legacy_error = any(
        "must_pass_constraints_must" in (issue.get("path") or "") for issue in issues
    )
    check(
        "T06.1 F01: must_pass_constraints_must is rejected",
        put_body.get("ok") is False and has_legacy_error,
        f"body={put_body}",
    )


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    global _only_test

    parser = argparse.ArgumentParser(description="QA API Contract Checks")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--test", default=None, help="Run only tests matching this prefix, e.g. T01.3"
    )
    args = parser.parse_args()

    _only_test = args.test
    base = args.api_base.rstrip("/")

    print(f"=== QA API Contract Checks (API: {base}) ===")

    run_t01(base)
    run_t02(base)
    run_t03(base)
    run_t04(base)
    run_t05(base)
    run_t06(base)

    print(f"\n{'=' * 40}")
    print(f"  PASS: {_pass}  FAIL: {_fail}")
    print(f"{'=' * 40}")
    if _fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
