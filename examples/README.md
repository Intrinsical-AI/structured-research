# Examples Guide

This folder contains reusable payloads, datasets and QA assets.

## What is included

- `examples/job_search/profile_example/`: reusable request payload fragments such as `job.json` and `candidate.json`
- `examples/job_search/run_request_example.json`: sample `RunScoreRequest`
- `examples/gen_cv/request_example.json`: sample `GenCVRequest`
- `examples/qa/data/*.jsonl`: synthetic datasets (`valid_batch`, `edge_cases`, `hostile`)
- `examples/qa/scripts/`: CLI and HTTP smoke checks

Runtime profiles are loaded from `config/`, not from `examples/`.

## Quick Checks

### Job search prompt

```bash
uv run structured-search task job_search prompt \
  --profile-id profile_example \
  --step S3_execute \
  --output /tmp/examples_prompt.md
```

### Job search run

```bash
uv run structured-search task job_search run \
  --profile-id profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/examples_scored.jsonl
```

### Job search run-validate

```bash
uv run structured-search task job_search run-validate \
  --request examples/job_search/run_request_example.json
```

### GEN_CV action

```bash
uv run structured-search task gen_cv action \
  --action-name gen-cv \
  --request examples/gen_cv/request_example.json
```

## QA Automation

```bash
bash examples/qa/scripts/smoke.sh
python3 examples/qa/scripts/api_checks.py
```
