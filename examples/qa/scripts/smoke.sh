#!/usr/bin/env bash
# QA Smoke Test — structured-research
# Tests core CLI flows without requiring a running API.
# Usage: bash examples/qa/scripts/smoke.sh [--profiles-base PATH]
set -euo pipefail

PROFILES_BASE="${1:-examples}"
PASS=0; FAIL=0

pass() { echo "  PASS $1"; ((PASS++)); return 0; }
fail() { echo "  FAIL $1 — $2"; ((FAIL++)); return 0; }

require_cmd() { command -v "$1" &>/dev/null || { echo "ERROR: '$1' not found"; exit 1; }; }

require_cmd uv
require_cmd python3

CLI="uv run structured-search"
ENV_PREFIX="PROFILES_BASE=$PROFILES_BASE"

echo "=== QA Smoke Tests (PROFILES_BASE=$PROFILES_BASE) ==="
echo ""

# ── T01: Prompt generation ──────────────────────────────────────────────────
echo "── T01: Prompt Generation ──"

OUT=$(eval "$ENV_PREFIX $CLI task job_search prompt \
  --profile profile_example --step S3_execute 2>&1") && \
  echo "$OUT" | grep -q "Search Constraints" && \
  pass "T01.1 prompt rendered with constraints" || \
  fail "T01.1 prompt generation" "output: ${OUT:0:200}"

set +e
OUT2=$(eval "$ENV_PREFIX $CLI task job_search prompt \
  --profile does_not_exist_xyz --step S3_execute 2>&1")
RC=$?
set -e
[[ $RC -ne 0 ]] && pass "T01.2 unknown profile exits non-zero" || \
  fail "T01.2 unknown profile" "expected non-zero exit"

echo ""

# ── T02: JSONL Validation (via run) ────────────────────────────────────────
echo "── T02: Scoring Run (valid_batch.jsonl) ──"

OUT_SCORED=$(mktemp /tmp/qa_scored_XXXXX.jsonl)

eval "$ENV_PREFIX $CLI task job_search run \
  --profile profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output $OUT_SCORED 2>&1" >/dev/null && \
  pass "T02.1 run command exits 0" || \
  fail "T02.1 run command" "non-zero exit"

LINE_COUNT=$(wc -l < "$OUT_SCORED")
[[ "$LINE_COUNT" -eq 5 ]] && \
  pass "T02.2 output has 5 lines" || \
  fail "T02.2 output line count" "got $LINE_COUNT, expected 5"

GATE_FAILS=$(python3 -c "
import json, sys
fails = [json.loads(l) for l in open('$OUT_SCORED') if not json.loads(l).get('gate_passed')]
print(len(fails))
")
[[ "$GATE_FAILS" -eq 1 ]] && \
  pass "T02.3 exactly 1 gate failure (QA-V03 on_site)" || \
  fail "T02.3 gate failures count" "got $GATE_FAILS, expected 1"

# Verify QA-V01 score = 9.5
python3 -c "
import json, sys
for r in map(json.loads, open('$OUT_SCORED')):
    if r['id'] == 'QA-V01':
        s = r.get('score')
        sys.exit(0 if s == 9.5 else 1)
" && pass "T02.4 QA-V01 score=9.5" || fail "T02.4 QA-V01 score" "expected 9.5"

python3 -c "
import json, sys
for r in map(json.loads, open('$OUT_SCORED')):
    if r['id'] == 'QA-V03':
        sys.exit(0 if r.get('gate_passed') == False else 1)
" && pass "T02.5 QA-V03 gate_passed=false" || fail "T02.5 QA-V03 gate" "expected false"

rm -f "$OUT_SCORED"
echo ""

# ── T03: Weighted bundle ────────────────────────────────────────────────────
echo "── T03: Score Clamping (qa_weighted) ──"

OUT_W=$(mktemp /tmp/qa_weighted_XXXXX.jsonl)

eval "$ENV_PREFIX $CLI task job_search run \
  --profile qa_weighted \
  --input examples/qa/data/edge_cases.jsonl \
  --output $OUT_W 2>&1" >/dev/null && \
  pass "T03.1 qa_weighted run exits 0" || \
  fail "T03.1 qa_weighted run" "non-zero exit"

python3 -c "
import json, sys
for r in map(json.loads, open('$OUT_W')):
    if r['id'] == 'QA-E01':
        score = r.get('score')
        raw   = r.get('score_breakdown', {}).get('raw_score', 0)
        sys.exit(0 if score == 10.0 and raw > 10.0 else 1)
" && pass "T03.2 QA-E01 score clamped to 10.0 (raw>10)" || \
  fail "T03.2 score clamp at 10" "check QA-E01 in $OUT_W"

rm -f "$OUT_W"
echo ""

# ── T04: Open bundle (penalty clamp at 0) ──────────────────────────────────
echo "── T04: Score Clamping (qa_open) ──"

OUT_O=$(mktemp /tmp/qa_open_XXXXX.jsonl)

eval "$ENV_PREFIX $CLI task job_search run \
  --profile qa_open \
  --input examples/qa/data/edge_cases.jsonl \
  --output $OUT_O 2>&1" >/dev/null && \
  pass "T04.1 qa_open run exits 0" || \
  fail "T04.1 qa_open run" "non-zero exit"

python3 -c "
import json, sys
for r in map(json.loads, open('$OUT_O')):
    if r['id'] == 'QA-E02':
        score = r.get('score')
        raw   = r.get('score_breakdown', {}).get('raw_score', 0)
        sys.exit(0 if score == 0.0 and raw < 0 else 1)
" && pass "T04.2 QA-E02 score clamped to 0.0 (raw<0)" || \
  fail "T04.2 score clamp at 0" "check QA-E02 in $OUT_O"

rm -f "$OUT_O"
echo ""

# ── T05: require_any gates ──────────────────────────────────────────────────
echo "── T05: require_any gates (qa_require_any) ──"

OUT_RA=$(mktemp /tmp/qa_rany_XXXXX.jsonl)

eval "$ENV_PREFIX $CLI task job_search run \
  --profile qa_require_any \
  --input examples/qa/data/edge_cases.jsonl \
  --output $OUT_RA 2>&1" >/dev/null && \
  pass "T05.1 qa_require_any run exits 0" || \
  fail "T05.1 qa_require_any run" "non-zero exit"

python3 -c "
import json, sys
results = {r['id']: r for r in map(json.loads, open('$OUT_RA'))}
e12 = results.get('QA-E12', {})
e13 = results.get('QA-E13', {})
e14 = results.get('QA-E14', {})
ok = (e12.get('gate_passed') == True and
      e13.get('gate_passed') == False and
      e14.get('gate_passed') == True)
sys.exit(0 if ok else 1)
" && pass "T05.2 require_any: E12=pass, E13=fail, E14=pass" || \
  fail "T05.2 require_any logic" "check E12/E13/E14 in $OUT_RA"

python3 -c "
import json, sys
for r in map(json.loads, open('$OUT_RA')):
    if r['id'] == 'QA-E13':
        gf = r.get('gate_failures', [])
        sys.exit(0 if any('all failed' in f for f in gf) else 1)
" && pass "T05.3 E13 gate_failures contains 'all failed'" || \
  fail "T05.3 require_any all-fail message" "check QA-E13"

rm -f "$OUT_RA"
echo ""

# ── T06: neutral_if_na ─────────────────────────────────────────────────────
echo "── T06: neutral_if_na (qa_neutral_na) ──"

OUT_NA=$(mktemp /tmp/qa_nna_XXXXX.jsonl)

eval "$ENV_PREFIX $CLI task job_search run \
  --profile qa_neutral_na \
  --input examples/qa/data/edge_cases.jsonl \
  --output $OUT_NA 2>&1" >/dev/null && \
  pass "T06.1 qa_neutral_na run exits 0" || \
  fail "T06.1 qa_neutral_na run" "non-zero exit"

python3 -c "
import json, sys
results = {r['id']: r for r in map(json.loads, open('$OUT_NA'))}
e09 = results.get('QA-E09', {})  # absent field -> neutral -> PASS
e10 = results.get('QA-E10', {})  # null field + neutral_if_na=true -> PASS
ok = (e09.get('gate_passed') == True and e10.get('gate_passed') == True)
sys.exit(0 if ok else 1)
" && pass "T06.2 neutral_if_na: absent=PASS, null=PASS (F02 fixed)" || \
  fail "T06.2 neutral_if_na logic" "check E09/E10 in $OUT_NA"

rm -f "$OUT_NA"
echo ""

# ── T07: CLI error paths ────────────────────────────────────────────────────
echo "── T07: CLI Error Paths ──"

eval "$ENV_PREFIX $CLI task job_search run \
  --profile profile_example \
  --input /tmp/this_file_does_not_exist_qa.jsonl \
  --output /tmp/qa_out.jsonl 2>&1" && \
  fail "T07.1 missing input" "expected non-zero exit" || \
  pass "T07.1 missing input file exits non-zero"

eval "$ENV_PREFIX $CLI task job_search prompt \
  --profile profile_example --step INVALID_STEP_XYZ 2>&1" && \
  fail "T07.2 invalid step" "expected non-zero exit" || \
  pass "T07.2 invalid step exits non-zero"

echo ""

# ── Summary ────────────────────────────────────────────────────────────────
echo "══════════════════════════════════"
echo "  PASS: $PASS  FAIL: $FAIL"
echo "══════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo "All smoke tests passed." || { echo "Some tests failed."; exit 1; }
