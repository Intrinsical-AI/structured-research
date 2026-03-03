# Structured Search with LLMs

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI 0.115+](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`structured-search` is a local-first framework for **task-scoped, auditable LLM workflows**.

Core characteristics:
- probabilistic upstream extraction/generation via LLM
- deterministic schema validation
- deterministic gates + soft scoring
- task/plugin architecture (`job_search`, `product_search`, `gen_cv`)

## Quick Start

### 1) Install dependencies

```bash
uv sync
```

### 2) Install API/UI extras (recommended for local dev)

```bash
uv run structured-search dev api-install
uv run structured-search dev ui-install
```

### 3) Start API + UI

```bash
uv run structured-search dev all --reload
```

### 4) List tasks and capabilities

```bash
uv run structured-search tasks list
```

### 5) Run a `job_search` workflow

```bash
uv run structured-search task job_search prompt \
  --profile profile_1 \
  --step S3_execute \
  --output /tmp/job_search_prompt.md

uv run structured-search task job_search run \
  --profile profile_1 \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/jobs_scored.jsonl
```

### 6) Run `gen_cv` action

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

## API (v1)

Task-scoped endpoints under `/v1`:
- `GET /v1/tasks`
- `GET /v1/tasks/{task_id}/profiles`
- `GET|PUT /v1/tasks/{task_id}/profiles/{profile_id}/bundle`
- `POST /v1/tasks/{task_id}/prompt/generate`
- `POST /v1/tasks/{task_id}/jsonl/validate`
- `POST /v1/tasks/{task_id}/run/validate`
- `POST /v1/tasks/{task_id}/run`
- `POST /v1/tasks/{task_id}/actions/gen-cv`

Notes:
- unsupported capabilities return `422` (for example, `/run` on `gen_cv`)
- unknown task IDs return `404`
- legacy endpoints (`/v1/job-search/*`, `/v1/gen-cv`) are removed

## Built-in Tasks

| Task ID | Main capabilities |
| --- | --- |
| `job_search` | `prompt`, `jsonl_validate`, `run` |
| `product_search` | `prompt`, `jsonl_validate`, `run` |
| `gen_cv` | `action:gen-cv` |

## Documentation

- [docs/USAGE.md](./docs/USAGE.md): setup and operational commands
- [docs/API_CONTRACT_V1.md](./docs/API_CONTRACT_V1.md): HTTP contract
- [docs/CONFIG_TASK.md](./docs/CONFIG_TASK.md): bundle/template semantics
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md): architecture and boundaries

## Repository Layout

```text
src/structured_search/
  api/
  application/
    common/
    core/
      plugins/
    gen_cv/
  contracts.py
  domain/
    common/
    job_search/
    product_search/
    gen_cv/
  infra/
  ports/
  tools/

config/
  job_search/
  product_search/
  gen_cv/
  templates/

resources/prompts/
  _base/
  job_search/
  product_search/
  gen_cv/
```

## License

[MIT](./LICENSE)
