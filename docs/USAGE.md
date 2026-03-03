# Usage Guide

Operational guide for task-scoped `structured-search`.

## 1) Prerequisites

- Python `>=3.12`
- `uv`
- Node.js + `npm` (for UI)
- Optional: local Ollama (for real `gen_cv` generation without fallback)

## 2) Setup

```bash
uv sync
uv run structured-search dev api-install
uv run structured-search dev ui-install
```

## 3) Run API + UI

```bash
uv run structured-search dev all --reload
```

Useful variants:

```bash
uv run structured-search dev api --reload
uv run structured-search dev ui --api-base http://127.0.0.1:8000/v1
```

## 4) Discover tasks

```bash
uv run structured-search tasks list
```

Current built-in tasks:
- `job_search` (`prompt`, `jsonl_validate`, `run`)
- `product_search` (`prompt`, `jsonl_validate`, `run`)
- `gen_cv` (`action:gen-cv`)

## 5) Profiles and configuration

Profiles are loaded from:
- `config/{task_id}/{profile_id}/bundle.json`

You can override the base directory with:

```bash
export PROFILES_BASE=examples
```

## 6) Task workflows

### 6.1 Job search: prompt generation

```bash
uv run structured-search task job_search prompt \
  --profile profile_1 \
  --step S3_execute \
  --output /tmp/job_search_prompt.md
```

### 6.2 Job search: deterministic run

```bash
uv run structured-search task job_search run \
  --profile profile_1 \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/jobs_scored.jsonl
```

### 6.3 Job search: dry-run validation (`/run/validate` equivalent)

Using full request payload:

```bash
cat > /tmp/run_request.json << 'JSON'
{
  "profile_id": "profile_1",
  "records": [
    {
      "id": "QA-V01",
      "source": "linkedin",
      "title": "Senior Python Backend Engineer",
      "company": "Acme Corp",
      "stack": ["python", "typescript"],
      "modality": "remote",
      "seniority": {"level": "senior"},
      "apply_url": "https://acme.com/apply/001",
      "geo": {"region": "EU"},
      "evidence": [],
      "facts": [],
      "inferences": [],
      "anomalies": [],
      "incomplete": false
    }
  ],
  "require_snapshot": false
}
JSON

uv run structured-search task job_search run-validate \
  --request /tmp/run_request.json
```

### 6.4 Product search: prompt + run

```bash
uv run structured-search task product_search prompt \
  --profile profile_default \
  --step S3_execute

uv run structured-search task product_search run \
  --profile profile_default \
  --input <your_product_records.jsonl> \
  --output /tmp/products_scored.jsonl
```

### 6.5 GEN_CV action

```bash
cat > /tmp/gen_cv_request.json << 'JSON'
{
  "profile_id": "profile_1",
  "job": {
    "id": "job-001",
    "title": "Senior Backend Engineer",
    "company": "Acme",
    "stack": ["Python", "FastAPI"]
  },
  "candidate_profile": {
    "id": "cand-1",
    "name": "Jane Doe",
    "seniority": "senior"
  },
  "allow_mock_fallback": true
}
JSON

uv run structured-search task gen_cv action \
  --name gen-cv \
  --request /tmp/gen_cv_request.json
```

## 7) API mapping

- `GET /v1/tasks`
- `GET /v1/tasks/{task_id}/profiles`
- `GET /v1/tasks/{task_id}/profiles/{profile_id}/bundle`
- `PUT /v1/tasks/{task_id}/profiles/{profile_id}/bundle`
- `POST /v1/tasks/{task_id}/prompt/generate`
- `POST /v1/tasks/{task_id}/jsonl/validate`
- `POST /v1/tasks/{task_id}/run/validate`
- `POST /v1/tasks/{task_id}/run`
- `POST /v1/tasks/{task_id}/actions/gen-cv`

## 8) Quality checks

```bash
uv run structured-search quality lint
uv run structured-search quality format
uv run structured-search quality test --quick
uv run structured-search quality arch-lint
```

## 9) Contract sync for UI

```bash
uv run structured-search tools export-openapi --output docs/openapi_v1.json
uv run structured-search tools export-ui-types \
  --openapi docs/openapi_v1.json \
  --output ui/lib/generated/api-types.ts
```
