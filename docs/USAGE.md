# Usage Guide

Operational guide for task-scoped `structured-search`.

## 1) Prerequisites

- Python `>=3.12`
- `uv`
- Node.js + `npm` for the UI
- Optional: local Ollama for real `gen_cv` generation without fallback

## 2) Setup

```bash
uv sync
uv run structured-search dev api-install
uv run structured-search dev ui-install
```

## 3) Runtime Profiles

- Canonical runtime profiles live in `config/{task_id}/{profile_id}/bundle.json`.
- Built-in demo profiles use `profile_example`.
- `examples/` only contains reusable payloads, datasets and QA scripts.
- `PROFILES_BASE` can still override the profile root when needed.

## 4) Discover Tasks

```bash
uv run structured-search tasks list
```

## 5) Task Workflows

### 5.1 Job search prompt generation

```bash
uv run structured-search task job_search prompt \
  --profile-id profile_example \
  --step S3_execute \
  --output /tmp/job_search_prompt.md
```

### 5.2 Job search deterministic run

```bash
uv run structured-search task job_search run \
  --profile-id profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/jobs_scored.jsonl
```

### 5.3 Job search dry-run validation

```bash
uv run structured-search task job_search run-validate \
  --request examples/job_search/run_request_example.json
```

### 5.4 Product search prompt + run

```bash
uv run structured-search task product_search prompt \
  --profile-id profile_example \
  --step S3_execute

uv run structured-search task product_search run \
  --profile-id profile_example \
  --input <product_records.jsonl> \
  --output /tmp/products_scored.jsonl
```

### 5.5 GEN_CV action

```bash
uv run structured-search task gen_cv action \
  --action-name gen-cv \
  --request examples/gen_cv/request_example.json
```

## 6) API and UI

```bash
uv run structured-search dev api --reload
uv run structured-search dev ui --api-base http://127.0.0.1:8000/v1
uv run structured-search dev all --reload
```

## 7) API Mapping

- `GET /v1/tasks`
- `GET /v1/tasks/{task_id}/profiles`
- `GET /v1/tasks/{task_id}/profiles/{profile_id}/bundle`
- `PUT /v1/tasks/{task_id}/profiles/{profile_id}/bundle`
- `POST /v1/tasks/{task_id}/prompt/generate`
- `POST /v1/tasks/{task_id}/jsonl/validate`
- `POST /v1/tasks/{task_id}/run/validate`
- `POST /v1/tasks/{task_id}/run`
- `POST /v1/tasks/{task_id}/actions/gen-cv`

## 8) Quality Checks

```bash
uv run structured-search quality lint
uv run structured-search quality format
uv run structured-search quality test --quick
uv run structured-search quality arch-lint
uv run structured-search tools validate-atoms
```

## 9) Contract Sync for UI

```bash
uv run structured-search tools export-openapi --output docs/openapi_v1.json
uv run structured-search tools export-ui-types \
  --openapi docs/openapi_v1.json \
  --output ui/lib/generated/api-types.ts
```
