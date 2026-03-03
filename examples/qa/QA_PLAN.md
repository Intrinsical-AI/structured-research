# Hostile QA Plan — structured-research

## Meta

| Attribute | Value |
|-----------|-------|
| Scope     | Full system QA, current release |
| Approach  | Manual verification via commands, synthetic datasets, and scripted checks |
| LLM dep.  | None (all scoring is deterministic; LLM tests are fallback-path only) |
| Assets    | `examples/job_search/qa_*/` (profiles), `examples/qa/data/` (datasets), `examples/qa/scripts/` |

---

## Quick Setup

```bash
# All QA profiles live under examples/job_search/ as subdirectories.
# Point the API at the examples directory so QA profiles are immediately available.
export PROFILES_BASE=examples

# Start API (in one terminal):
make api
# Or without make:
PROFILES_BASE=examples uv run structured-search dev api

# Verify QA profiles are loaded:
curl -s http://localhost:8000/v1/tasks/job_search/profiles | jq '.[].profile_id'
# Expected: [..., "qa_strict", "qa_weighted", "qa_open", "qa_neutral_na", "qa_require_any"]

# Run all scripted checks:
bash examples/qa/scripts/smoke.sh
python3 examples/qa/scripts/api_checks.py
```

---

## Known Findings (historical + status)

### F01 — `must_pass_constraints_must` legacy field (resolved via breaking change)
**Location**: `profile_example/bundle.json` and any user bundle with this field.
Breaking update: `task.gates` now forbids unknown fields; this key is rejected at bundle save.
**Verify**: PUT bundle with `must_pass_constraints_must: false` and confirm `ok=false`.

### F02 — Explicit `null` bypasses `neutral_if_na` (resolved)
**Location**: `infra/scoring.py:_check_rule()`
```python
if value in (_MISSING, None):
    return None if rule.neutral_if_na else False
```
A field explicitly set to `null` is now treated as neutral when `neutral_if_na=true`
(same behavior as a missing key). With `neutral_if_na=false`, `null` still fails.
**Verify**: T02.9 below.

### F03 — `inferences` expects `list[InferenceRecord]`, not `list[str]`
**Location**: `domain/models.py:BaseResult.inferences`
The field is typed `list[InferenceRecord]` (complex objects). A JSONL record with
`"inferences": ["salary_inferred"]` (list of strings) will fail schema validation.
**Risk**: LLM-generated output that emits inferences as plain strings will be rejected
at ingest, silently discarding records.
**Verify**: T03 hostile.jsonl line 17.

### F04 — Score denominator not disclosed in API response
`RunScoreResponse.metrics.processed` counts scored records, but there's no field
indicating how many records **passed gates** vs. **failed gates**. Users cannot tell
gate pass-rate from the response alone; they must count `gate_passed: true/false`
in the `scored_records` array themselves.

### F05 — `required_evidence_fields` prefix matching is asymmetric
**Location**: `infra/scoring.py:_evaluate_required_evidence_failures()`
```python
if required not in evidence_fields and not any(
    required.startswith(f"{ef}.") for ef in evidence_fields
):
```
The check passes if `required` starts with any known evidence field (e.g., `required="apply_url.href"`
passes if `"apply_url"` is in evidence). But the inverse is not checked: if `required="apply_url"`
and the evidence has field `"apply_url.href"`, it **fails** because `"apply_url"` is not
`startswith("apply_url.href.")`.
**Verify**: T02.13 below.

---

## T01 — Happy Path Smoke

### T01.1 — Prompt generation (CLI)
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search prompt \
  --profile profile_example --step S3_execute
```
**Expected**: Prompt rendered to stdout. Contains `## Search Constraints` section.
Exits 0.

### T01.2 — Prompt generation (API)
```bash
curl -s -X POST http://localhost:8000/v1/tasks/job_search/prompt/generate \
  -H "Content-Type: application/json" \
  -d '{"profile_id": "profile_example", "step": "S3_execute"}' | jq '{constraints_embedded, prompt_hash}'
```
**Expected**: `constraints_embedded: true`, `prompt_hash` starts with `sha256:`.

### T01.3 — JSONL validation: clean batch
```bash
python3 examples/qa/scripts/api_checks.py --test T01.3
```
Or manually:
```bash
curl -s -X POST http://localhost:8000/v1/tasks/job_search/jsonl/validate \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json, pathlib
raw = pathlib.Path('examples/qa/data/valid_batch.jsonl').read_text()
print(json.dumps({'raw_jsonl': raw, 'profile_id': 'profile_example'}))
")" | jq '.metrics'
```
**Expected**: `schema_valid_records: 5`, `invalid_lines: 0`.

### T01.4 — Run scoring: clean batch (CLI)
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/qa_v01_scored.jsonl

wc -l /tmp/qa_v01_scored.jsonl   # Expected: 5
```

### T01.5 — Run scoring: dry-run validate (API)
```bash
python3 examples/qa/scripts/api_checks.py --test T01.5
```
**Expected**: 200 OK, `valid: true`.

### T01.6 — Gen CV prompt
```bash
PROFILES_BASE=examples \
  uv run structured-search task gen_cv action --name gen-cv prompt \
  --job examples/job_search/profile_example/job.json \
  --candidate examples/job_search/profile_example/candidate.json \
  --profile profile_example \
  --atoms-dir examples/job_search/profile_example/atoms \
  --output /tmp/qa_cv_prompt.md
```
**Expected**: Markdown prompt with atoms embedded. Exits 0.

### T01.7 — List profiles
```bash
curl -s http://localhost:8000/v1/tasks/job_search/profiles | jq '.[].profile_id'
```
**Expected**: at least `profile_example`, `qa_strict`, `qa_weighted`, `qa_open`,
`qa_neutral_na`, `qa_require_any`.

---

## T02 — Scoring Engine Battle Tests

### Score expectations for `valid_batch.jsonl` against `profile_example`

| ID      | Gate | Expected Score | Reason |
|---------|------|---------------|--------|
| QA-V01  | PASS | 9.5           | base(5)+prefer(2.5)+salary(1.5)+evidence(0.5) |
| QA-V02  | PASS | 4.0           | base(5)+no_prefer(0)-missing_salary(1.0) |
| QA-V03  | FAIL | null          | modality=on_site violates must |
| QA-V04  | PASS | 8.0           | base(5)+prefer(2.5)-avoid(1.0)+salary(1.5); no evidence |
| QA-V05  | PASS | 4.5           | base(5)+prefer(2.5)-missing_salary(1.0)-incomplete(2.0) |

**How to verify**:
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/qa_scores.jsonl

# Inspect scores:
python3 -c "
import json
for line in open('/tmp/qa_scores.jsonl'):
    r = json.loads(line)
    print(r['id'], r.get('gate_passed'), r.get('score'))
"
```

### T02.1 — Score clamping at 10.0 (QA-E01 with qa_weighted)
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile qa_weighted \
  --input examples/qa/data/edge_cases.jsonl \
  --output /tmp/qa_edge_scored.jsonl

python3 -c "
import json
for r in map(json.loads, open('/tmp/qa_edge_scored.jsonl')):
    if r['id'] == 'QA-E01':
        assert r['score'] == 10.0, f'Expected 10.0, got {r[\"score\"]}'
        print('T02.1 PASS: score correctly clamped to 10.0')
        print('  raw_score:', r['score_breakdown']['raw_score'])
"
```
**Expected**: `score=10.0`, `raw_score > 10.0` (should be 17.0).

### T02.2 — Score clamping at 0.0 (QA-E02 with qa_open)
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile qa_open \
  --input examples/qa/data/edge_cases.jsonl \
  --output /tmp/qa_open_scored.jsonl

python3 -c "
import json
for r in map(json.loads, open('/tmp/qa_open_scored.jsonl')):
    if r['id'] == 'QA-E02':
        assert r['score'] == 0.0, f'Expected 0.0, got {r[\"score\"]}'
        print('T02.2 PASS: score correctly clamped to 0.0')
        print('  raw_score:', r['score_breakdown']['raw_score'])
"
```
**Expected**: `score=0.0`, `raw_score < 0` (should be -7.5 or lower).

### T02.3 — Gate fail via must rule
**Input**: QA-V03 (modality=on_site).
**Expected**: `gate_passed=false`, `gate_failures` contains `"constraint.must: I only want remote or hybrid jobs."`.

### T02.4 — Gate fail via hard_filter (qa_strict, salary below threshold)
```bash
# Score QA-E05 (salary=30000, below qa_strict threshold of 50000) with qa_strict
python3 -c "
import json
for r in map(json.loads, open('/tmp/qa_strict_scored.jsonl')):
    if r['id'] == 'QA-E05':
        print('gate_passed:', r['gate_passed'])
        print('gate_failures:', r['gate_failures'])
"
```
**Expected**: `gate_passed=false`, `gate_failures` contains a hard_filter failure message
for `economics.salary_eur_gross`.

### T02.5 — Gate fail via anomaly rejection
**Input**: QA-V08 / QA-E08 (anomalies: ["prompt_injection_suspected"]) with profile_example.
**Expected**: `gate_passed=false`, `gate_failures` contains `"anomaly: prompt_injection_suspected"`.

### T02.6 — Gate fail via missing required evidence (qa_strict)
**Input**: A record with no evidence anchors, scored against qa_strict.
**Expected**: `gate_passed=false`, `gate_failures` contains `"missing_evidence: apply_url"`.
See QA-E11 in edge_cases.jsonl.

### T02.7 — neutral_if_na=true + field absent → gate PASS
**Input**: QA-E09 (no visa_sponsorship_offered field) with qa_neutral_na.
**Expected**: `gate_passed=true` (the must rule with neutral_if_na=true returns None, not False).

### T02.8 — neutral_if_na=false + field absent → gate FAIL (default behaviour)
**Input**: any record missing a must-required field without neutral_if_na, against qa_strict.

### T02.9 — explicit null is neutral when `neutral_if_na=true` (Finding F02 fixed)
**Input**: QA-E10 (visa_sponsorship_offered: null) with qa_neutral_na.
```bash
python3 -c "
import json
for r in map(json.loads, open('/tmp/qa_neutral_na_scored.jsonl')):
    if r['id'] == 'QA-E10':
        # null field is neutral when neutral_if_na=true
        print('gate_passed:', r['gate_passed'])   # EXPECTED: true
        print('gate_failures:', r['gate_failures'])
"
```
**Expected**: `gate_passed=true` — explicit null is neutral when `neutral_if_na=true`.

### T02.10 — hard_filters_mode=require_any: one passes → gate PASS
**Input**: QA-E12 (modality=hybrid, geo.country=Spain) with qa_require_any.
qa_require_any hard_filters: [modality=remote, geo.country=Spain], mode=require_any.
**Expected**: `gate_passed=true` (geo.country=Spain passes; at least one passes).

### T02.11 — hard_filters_mode=require_any: all fail → gate FAIL
**Input**: QA-E13 (modality=hybrid, geo.country=Germany) with qa_require_any.
**Expected**: `gate_passed=false`, `gate_failures=["hard_filters: all failed"]`.

### T02.12 — weighted operator: all values match → full weight sum
**Input**: QA-E01 (stack has all 5 qa_weighted values).
```python
# Stack: python(3.0) + typescript(2.0) + react(1.5) + kubernetes(2.5) + go(1.0) = 10.0
```
**Expected**: `score_breakdown.boosts` includes ~10.0 from prefer rule.

### T02.13 — required_evidence prefix asymmetry (Finding F05)
Configure `required_evidence_fields: ["apply_url"]`.
Score a record where evidence has `field: "apply_url.href"` (not exactly "apply_url").
**Expected**: FAILS — the check only looks for exact match OR record field starting with
evidence field path; does NOT match partial prefix in the other direction.

### T02.14 — Old posting penalty triggers
**Input**: QA-E05 (recency.activity_age_days=90) with qa_open (threshold=30).
**Expected**: `score_breakdown.penalties >= 2.0` from old_posting.

### T02.15 — Excess hybrid days penalty
**Input**: QA-E06 (onsite_days_per_week=5.0) with qa_open (threshold=3).
**Expected**: `score_breakdown.penalties >= 2.0` from excess_hybrid.

### T02.16 — `must_pass_constraints_must` rejected at validation (Finding F01 fixed)
```bash
# Copy qa_strict profile and set legacy field; PUT should return ok=false
curl -s -X PUT http://localhost:8000/v1/tasks/job_search/profiles/qa_strict_test/bundle \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
b = json.load(open('examples/job_search/qa_strict/bundle.json'))
b['profile_id'] = 'qa_strict_test'
b['task']['gates']['must_pass_constraints_must'] = False
print(json.dumps(b))
")"

# Score QA-V03 (modality=on_site violates must) against qa_strict_test
# Expected: gate STILL FAILS (flag is ignored)
```

---

## T03 — JSONL Ingestion Hostility

Run against the `/v1/tasks/job_search/jsonl/validate` endpoint.

```bash
python3 examples/qa/scripts/api_checks.py --test T03
```

### Expected results for `hostile.jsonl` (17 lines):

| Line | ID / Content | Expected Outcome |
|------|-------------|-----------------|
| 1 | QA-H-CTRL-01 | valid ✓ |
| 2 | `{` | parse error: unterminated JSON |
| 3 | `null` | parse/schema error: not an object |
| 4 | `[]` | schema error: not an object |
| 5 | `{"title":"x","company":"y"}` | schema error: missing required fields |
| 6 | `...modality:"office"` | schema error: invalid Literal value |
| 7 | `...seniority.level:"principal"` | schema error: not in Literal enum |
| 8 | `...apply_url:"not-a-url"` | schema error: invalid AnyUrl |
| 9 | QA-H-INJECT (prompt injection in title) | valid ✓ — schema doesn't detect injection |
| 10 | QA-H-LONGDESC (50KB description) | valid ✓ — no size limit enforced |
| 11 | `` (empty line) | parse error: empty |
| 12 | `   ` (whitespace) | parse error: whitespace |
| 13 | `// comment` | parse error: not JSON |
| 14 | `{...,}` trailing comma | parse error: syntax |
| 15 | QA-H-UNICODE | valid ✓ |
| 16 | QA-H-EXTRA-FIELDS | valid ✓ — extra="allow" |
| 17 | `...inferences:["string"]` | schema error: str not InferenceRecord |

**Key observations**:
- Line 9: Prompt injection in content fields passes schema validation. The system relies on
  the LLM having set `anomalies: ["prompt_injection_suspected"]`. Verify that the scoring
  engine then rejects it at the gate level.
- Line 10: No field length limit. A 50KB description is valid. Operator needs to document
  or enforce soft limits upstream.

---

## T04 — Bundle/Config Edge Cases

### T04.1 — Bundle with empty constraint arrays
```bash
curl -s -X PUT http://localhost:8000/v1/tasks/job_search/profiles/qa_minimal/bundle \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": "qa_minimal",
    "constraints": {"domain": "job_search", "must": [], "prefer": [], "avoid": []},
    "task": {
      "gates": {"hard_filters_mode": "require_all", "hard_filters": [], "reject_anomalies": [], "required_evidence_fields": []},
      "soft_scoring": {"formula_version": "v2_soft_after_gates", "prefer_weight_default": 1.0, "avoid_penalty_default": 1.0, "signal_boost": {"salary_disclosed": 0.0, "evidence_present": 0.0}, "penalties": {"incomplete": 0.0, "missing_salary": 0.0}}
    },
    "task_config": {"agent_name": "QA_MINIMAL", "version": "1.0", "language_priority": ["en"]},
    "user_profile": {"timezone": "UTC", "mobility": "remote", "currency_default": "EUR"}
  }' | jq '{ok, errors}'
```
**Expected**: `ok: true`, every record scores exactly 5.0 (base only, no rules).

### T04.2 — Invalid operator in constraint rule
```bash
curl -s -X PUT http://localhost:8000/v1/tasks/job_search/profiles/qa_badop/bundle \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": "qa_badop",
    "constraints": {
      "domain": "job_search",
      "must": [{"field": "modality", "op": "regex", "value": "remote.*"}]
    },
    "task": {"gates": {"hard_filters_mode": "require_all", "hard_filters": [], "reject_anomalies": [], "required_evidence_fields": []}, "soft_scoring": {"formula_version": "v2_soft_after_gates", "prefer_weight_default": 1.0, "avoid_penalty_default": 1.0}},
    "task_config": {"agent_name": "QA", "version": "1.0", "language_priority": ["en"]},
    "user_profile": {"timezone": "UTC", "mobility": "remote", "currency_default": "EUR"}
  }' | jq '{ok, errors}'
```
**Expected**: `ok: false`, error mentions invalid `op: regex`. The ConstraintRule model_validator
enforces valid operators.

### T04.3 — weighted op with mismatched weights length
```bash
# value has 3 items, weights has 2 → should fail validation
curl -s -X PUT ... -d '{
  "constraints": {"must": [{"field": "stack", "op": "weighted", "value": ["a","b","c"], "weights": [1.0, 2.0]}]}
  ...
}'
```
**Expected**: 422 / validation error: `"op 'weighted' requires len(weights) == len(value)"`.

### T04.4 — Profile ID path traversal (security)
```bash
curl -s http://localhost:8000/v1/tasks/job_search/profiles/../../etc/passwd/bundle
curl -s http://localhost:8000/v1/tasks/job_search/profiles/../../../sensitive/bundle
```
**Expected**: 404 (FileNotFoundError maps to 404). The filesystem path should be safely
resolved within PROFILES_BASE. Verify no actual file access outside the profiles directory.

### T04.5 — PUT bundle with profile_id mismatch
Send `profile_id: "profile_a"` in body to `PUT /v1/tasks/job_search/profiles/profile_b/bundle`.
**Expected**: The URL path ID (`profile_b`) takes precedence (per `bundle.profile_id = profile_id`
at line 118 of app.py). Body profile_id is overwritten. Verify the saved bundle has `profile_b`.

### T04.6 — compare op with non-numeric value
```bash
# op ">=" with value "fifty_thousand" (string)
```
**Expected**: 422 from `model_validator` in ConstraintRule: `"op '>=' requires numeric 'value'"`.

### T04.7 — list op with empty value list
```bash
# op "in" with value []
```
**Expected**: 422: `"op 'in' requires a non-empty 'value' list"`.

### T04.8 — Scoring unknown field path (dot path that doesn't exist on model)
```bash
# must rule: {"field": "totally.made.up.path", "op": "=", "value": "x"}
```
**Expected**: gate FAIL (field is _MISSING and neutral_if_na defaults to False → returns False).
The system doesn't raise an error for unknown paths; it treats them as missing.
**Risk**: Typo in a field path silently causes all records to fail the gate.

---

## T05 — API Contract Verification

### T05.1 — HTTP method violations
```bash
curl -s -X POST http://localhost:8000/v1/tasks/job_search/profiles     | jq .detail  # 405
curl -s -X GET  http://localhost:8000/v1/tasks/job_search/jsonl/validate | jq .detail # 405
```
**Expected**: 405 Method Not Allowed.

### T05.2 — Missing required body fields
```bash
curl -s -X POST http://localhost:8000/v1/tasks/job_search/jsonl/validate \
  -H "Content-Type: application/json" \
  -d '{}' | jq '{status: .status, detail: .detail}'
```
**Expected**: 422 Unprocessable Entity with field-level validation error for `raw_jsonl`.

### T05.3 — Nonexistent profile → 404
```bash
curl -s http://localhost:8000/v1/tasks/job_search/profiles/does_not_exist_xyz/bundle | jq .status
```
**Expected**: 404.

### T05.4 — require_snapshot=true when runs/ dir is missing
```bash
# Temporarily rename/remove the runs directory and run with require_snapshot=true
```
**Expected**: 500 RuntimeError (`snapshot_status` indicates failure, 500 returned because
`require_snapshot=true`).

### T05.5 — require_snapshot=false with unwriteable runs/ dir
**Expected**: 200 OK with `snapshot_status: "failed"` and `snapshot_error` populated.
The run succeeds even though snapshot failed.

### T05.6 — Empty JSONL input to /run
```bash
# raw_jsonl with empty string or only whitespace lines
```
**Expected**: 200 OK with `metrics.processed=0`, `metrics.loaded=0`.

### T05.7 — POST /v1/tasks/gen_cv/actions/gen-cv with allow_mock_fallback=true and no Ollama
```bash
curl -s -X POST http://localhost:8000/v1/tasks/gen_cv/actions/gen-cv \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
job = json.load(open('examples/job_search/profile_example/job.json'))
candidate = json.load(open('examples/job_search/profile_example/candidate.json'))
print(json.dumps({
  'profile_id': 'profile_example',
  'job': job,
  'candidate_profile': candidate,
  'allow_mock_fallback': True
}))
")" | jq '{status: (if .cv_markdown then \"ok\" else \"error\" end), fallback_used: .model_info.fallback_used}'
```
**Expected**: `status: "ok"`, `fallback_used: true` (MockLLM used since Ollama is not running).

### T05.8 — POST /v1/tasks/gen_cv/actions/gen-cv with allow_mock_fallback=false and no Ollama
**Expected**: 503 Service Unavailable.

### T05.9 — Concurrent POST /v1/tasks/job_search/run (race condition check)
```bash
# Fire 3 concurrent runs against different profiles
for p in qa_strict qa_weighted qa_open; do
  curl -s -X POST http://localhost:8000/v1/tasks/job_search/run \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
records = [json.loads(line) for line in open('examples/qa/data/valid_batch.jsonl') if line.strip()]
print(json.dumps({'profile_id': '$p', 'records': records, 'require_snapshot': False}))
")" &
done
wait
```
**Expected**: All 3 complete successfully without cross-contaminating results.
**What to look for**: `profile_id` in each response matches the request profile.

---

## T06 — Gen CV Edge Cases

### T06.1 — selected_claim_ids filtering
Pass a subset of valid claim IDs. Verify only those claims appear in the output.

### T06.2 — selected_claim_ids with non-existent IDs
Pass claim IDs that don't exist in the atoms. Verify they are silently filtered out
(not a 422 error), since `tasks/gen_cv/service.py` filters to available claim IDs.

### T06.3 — Missing atoms directory
Point to a non-existent atoms path. **Expected**: 404 or RuntimeError → 503.

### T06.4 — Atoms with broken references (validate-atoms tool)
```bash
PROFILES_BASE=examples \
  uv run structured-search tools validate-atoms --profile profile_example
```
**Expected**: No errors for the example atoms. Try inserting a broken `evidence_id` reference
in a claim atom and re-run — should report an error.

---

## T07 — CLI Edge Cases

### T07.1 — Unknown profile ID
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search prompt --profile does_not_exist --step S3_execute
```
**Expected**: Non-zero exit, clear error message.

### T07.2 — Missing input file to `run`
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile profile_example \
  --input /tmp/this_file_does_not_exist.jsonl \
  --output /tmp/out.jsonl
```
**Expected**: Non-zero exit, clear error (FileNotFoundError or equivalent).

### T07.3 — Invalid step name
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search prompt \
  --profile profile_example --step INVALID_STEP_XYZ
```
**Expected**: Non-zero exit, informative error about unknown step.

### T07.4 — Output directory does not exist
```bash
PROFILES_BASE=examples \
  uv run structured-search task job_search run \
  --profile profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/nonexistent_dir/output.jsonl
```
**Expected**: Clear error (directory creation or IOError).

### T07.5 — `tools validate-atoms` on malformed atoms
Temporarily corrupt an atom YAML file and run the validator.
**Expected**: Error report listing the broken atom, not a traceback.

---

## T08 — Cross-Cutting Concerns

### T08.1 — Metric events on errors
Call each endpoint in a way that triggers a 422 or 404. Verify that the metric emission
failure does NOT propagate to the user (wrapped in try/except in `_emit_metric_event`).

### T08.2 — Architecture import guard
```bash
uv run structured-search quality arch-lint
```
**Expected**: Exit 0. All import rules pass.

### T08.3 — Large JSONL batch (performance)
Send 500 records in a single run request. Measure wall-clock time.
Generate with: `python3 -c "
import json
base = json.load(open('/tmp/qa_v01_record.json'))  # use a valid record
for i in range(500):
    r = dict(base)
    r['id'] = f'PERF-{i:04d}'
    r['source_id'] = f'perf-{i}'
    print(json.dumps(r))
" > /tmp/qa_perf.jsonl`
**Expected**: Completes without timeout, score outputs are deterministic.

### T08.4 — Repeated identical runs are deterministic
Run the same JSONL input + profile twice. Diff the outputs (excluding `run_id`,
`extracted_at`, timestamps).
```bash
diff <(python3 -c "
import json, sys
for r in map(json.loads, open('/tmp/qa_run1.jsonl')):
    del r['run_id']
    print(json.dumps(r, sort_keys=True))
") <(python3 -c "
import json
for r in map(json.loads, open('/tmp/qa_run2.jsonl')):
    del r['run_id']
    print(json.dumps(r, sort_keys=True))
")
```
**Expected**: No diff (fully deterministic for identical input + config).

---

## Severity Matrix

| Finding | Severity | Impact |
|---------|----------|--------|
| F01: must_pass_constraints_must rejected | Resolved | Breaking validation prevents silent no-op |
| F02: explicit null honors neutral_if_na | Resolved | null is neutral when neutral_if_na=true |
| F03: inferences type mismatch | High | Records silently rejected at ingest |
| F04: no gate pass-rate in response | Low | Observability gap |
| F05: evidence prefix asymmetry | Medium | Unexpected gate behavior |
| T04.8: unknown field path silently fails gate | Medium | Typo causes all records to fail |
| T03 line 9: injection passes schema | Low-Medium | Design decision, needs documentation |
