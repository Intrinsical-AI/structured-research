# QA Plan

Reference commands for local QA using the canonical `config/` runtime layout.

## CLI smoke

```bash
bash examples/qa/scripts/smoke.sh
```

## API contract checks

Start the API:

```bash
uv run structured-search dev api --reload
```

Then run:

```bash
python3 examples/qa/scripts/api_checks.py
python3 examples/qa/scripts/api_checks.py --test T01.3
```

## Useful manual probes

```bash
uv run structured-search task job_search prompt \
  --profile-id profile_example \
  --step S3_execute

uv run structured-search task job_search run \
  --profile-id profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/jobs_scored.jsonl

uv run structured-search task job_search run-validate \
  --request examples/job_search/run_request_example.json

uv run structured-search task gen_cv action \
  --action-name gen-cv \
  --request examples/gen_cv/request_example.json

uv run structured-search tools validate-atoms
```
