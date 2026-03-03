# Usage Guide

Operational guide for `structured-search` (CLI, API, and UI).

For architecture and design constraints, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## 1) Prerequisites

- Python `>=3.12` + `uv` + Node.js + `npm` (for UI)

> Optional: local Ollama for `gen-cv`

## 2) Local Setup

### 2.1 Install

```bash
uv sync

# one-time setup
uv run structured-search dev api-install
uv run structured-search dev ui-install
```

### 2.2 Run API + UI

```bash
# run backend + frontend together
uv run structured-search dev all --reload
```

Advanced use and variants:
```bash
uv run structured-search dev api --reload
uv run structured-search dev ui --api-base http://127.0.0.1:8000/v1
uv run structured-search dev all --port 8010 --ui-port 3001 --reload
```

## 3) Profile Configuration

Goal: define runtime behavior (`constraints`, `task`, `task_config`) per profile `config/job_search/<profile_id>/bundle.json`.

For detailed template semantics and `bundle.json` mapping, see [CONFIG_TASK.md](./CONFIG_TASK.md).

- [constraints.template.json](../config/templates/constraints.template.json)
- [task.template.json](../config/templates/task.template.json)
- [task_config.template.json](../config/templates/task_config.template.json)
- [user_profile.template.json](../config/templates/user_profile.template.json)
- [schema.template.json](../config/templates/schema.template.json)
- [domain_schema.template.json](../config/templates/domain_schema.template.json)

## 4) Job Search Workflow

### 4.1 Generate deterministic prompt

```bash
uv run structured-search job-search prompt \
  --profile profile_1 \
  --step S3_execute \
  --output data/prompts/job_search_profile_1.md
```

Output: MarkDown (.md) file (or stdout if `--output` is omitted) with the custom prompt (base + task + context injection)

### 4.2 Run upstream extraction

Use generated prompt in your preferred LLM/search via Web UI (recommended over API for browsing/research tool integrations).

Output: JSONL file written to disk (example: `data/raw/jobs_features.jsonl`)

### 4.3 Run deterministic scoring

```bash
uv run structured-search job-search run \
  --profile profile_1 \
  --input data/raw/jobs_features.jsonl \
  --output data/processed/jobs_scored.jsonl
```

Optional constraints override:

```bash
uv run structured-search job-search run \
  --profile profile_1 \
  --input data/raw/jobs_features.jsonl \
  --output data/processed/jobs_scored.jsonl \
  --constraints config/custom_constraints.json
```

Output: scored JSONL with gate + score fields

### 4.4 Dry-run validate before `/run`

```bash
uv run structured-search job-search run-validate \
  --request run_request.json \
  --api-base http://127.0.0.1:8000/v1
```

Minimal `run_request.json`:

```json
{
  "profile_id": "profile_1",
  "records": [],
  "require_snapshot": false
}
```

Output: preflight summary (`ok`, validation checks, snapshot probe status)

## 5) Optional GEN_CV Workflow

### 5.1 Render GEN_CV prompt (grounded)

```bash
uv run structured-search gen-cv prompt \
  --job job_description.json \
  --candidate candidate_profile.json \
  --profile profile_1 \
  --atoms-dir config/job_search/profile_1/atoms \
  --output data/cvs/gen_cv_prompt.md
```

Output: `data/cvs/gen_cv_prompt.md` + base snapshot `data/cvs/gen_cv_prompt.base.md`

### 5.2 Generate CV JSON

```bash
uv run structured-search gen-cv run \
  --job job_description.json \
  --candidate candidate_profile.json \
  --atoms-dir config/job_search/profile_1/atoms \
  --llm-model lfm2.5-thinking \
  --output data/cvs/cv.json
```

## 6) Utility Commands

### 6.1 Validate atoms dataset

```bash
uv run structured-search tools validate-atoms \
  --atoms-dir config/job_search/profile_1/atoms \
  --schemas-dir config/job_search/profile_1/atoms/schemas \
  --canon-tags config/job_search/profile_1/atoms/canon_tags.yaml
```

### 6.2 Validate result files against task schema

```bash
uv run structured-search tools validate-results \
  --input-dir raw_results/job_search \
  --output-dir validated/job_search \
  --task job_search
```

### 6.3 Export API contract and generated UI types

```bash
make api-contract-export
make contract-sync
```

Equivalent direct commands:

```bash
uv run structured-search tools export-openapi --output docs/openapi_v1.json
uv run structured-search tools export-ui-types \
  --openapi docs/openapi_v1.json \
  --output ui/lib/generated/api-types.ts
```

## 7) Quality and Tests

Backend:

```bash
uv run structured-search quality lint
uv run structured-search quality test --quick
uv run structured-search quality arch-lint
```

Frontend:

```bash
cd ui
npm run lint
npm run test
```

Metrics tools:

```bash
uv run structured-search metrics report
uv run structured-search metrics populate \
  --api-base http://127.0.0.1:8000/v1 \
  --profile-id profile_1
```

## 8) CLI / API / UI Mapping

| Capability | CLI | API | UI |
|---|---|---|---|
| List profiles | - | `GET /v1/job-search/profiles` | Workspace profile selector |
| Load bundle | - | `GET /v1/job-search/profiles/{profile_id}/bundle` | Config tab |
| Save bundle | - | `PUT /v1/job-search/profiles/{profile_id}/bundle` | Config tab |
| Generate prompt | `job-search prompt` | `POST /v1/job-search/prompt/generate` | Prompt tab |
| Validate JSONL | - | `POST /v1/job-search/jsonl/validate` | JSONL tab |
| Run scoring | `job-search run` | `POST /v1/job-search/run` | Results tab |
| Run preflight validation | `job-search run-validate` | `POST /v1/job-search/run/validate` | API/CLI only |
| Generate CV | `gen-cv run` | `POST /v1/gen-cv` | CV tab |

## 9) Common Pitfalls

- Contract drift between `docs/API_CONTRACT_V1.md`, `src/structured_search/contracts.py`, and generated UI types.
- Adding business logic directly into API routes instead of application/task services.
- Breaking layer boundaries enforced by import-linter.
- Assuming `/run` snapshot persistence is mandatory when `require_snapshot=false`.
