# API Contract V1 (Task-Scoped)

Scope: HTTP contract for generic task-scoped workflows in `structured-search`.

Base URL: `/v1`

## 1) Tasks and capabilities

Use `GET /tasks` to discover capabilities at runtime.

Current built-in tasks:
- `job_search`: `prompt`, `jsonl_validate`, `run`
- `product_search`: `prompt`, `jsonl_validate`, `run`
- `gen_cv`: `action:gen-cv`
- `vuln_triage`: `jsonl_validate`, `run`

If a task does not support a capability endpoint, the API returns:
- `422` with detail like `does not support capability ...`

Unknown `task_id` returns:
- `404`

## 2) Endpoints

1. `GET /tasks`
- List registered tasks with `task_id`, `name`, and `capabilities`.

2. `GET /tasks/{task_id}/profiles`
- List profiles for a task (`id`, `name`, `updated_at`).

3. `GET /tasks/{task_id}/profiles/{profile_id}/bundle`
- Load bundle for editing.

4. `PUT /tasks/{task_id}/profiles/{profile_id}/bundle`
- Validate and save bundle.
- Always returns `200` with body:
  - `{ "ok": true, "version": "...", "errors": [...] }` on valid payload
  - `{ "ok": false, "errors": [...] }` on validation issues
- Path params override `task_id`/`profile_id` inside body.

5. `POST /tasks/{task_id}/prompt/generate`
- Request: `{ profile_id, step }`
- Response includes:
  - `prompt`
  - `constraints_embedded`
  - `prompt_hash`

6. `POST /tasks/{task_id}/jsonl/validate`
- Request: `{ profile_id, raw_jsonl }`
- Tolerant parsing + schema validation.
- Response metrics:
  - `total_lines`
  - `json_valid_lines`
  - `schema_valid_records`
  - `invalid_lines`

7. `POST /tasks/{task_id}/run/validate`
- Dry-run preflight for run execution.
- Request body uses `RunScoreRequest`.
- Response includes:
  - `ok`
  - `checks` (`profile_exists`, `constraints_valid`, `scoring_config_valid`, `all_records_schema_valid`, snapshot I/O probe)
  - `snapshot_probe_dir` / `snapshot_probe_error`

8. `POST /tasks/{task_id}/run`
- Deterministic gate + soft-scoring execution.
- Request body uses `RunScoreRequest`:
  - `profile_id` (required)
  - `records` (required)
  - `require_snapshot` (optional, default `false`)
- Response includes:
  - `run_id`, `profile_id`, `scored_records`, `errors`
  - `metrics` (`loaded`, `processed`, `skipped`, `gate_passed`, `gate_failed`, `gate_pass_rate`, `started_at`, `finished_at`)
  - `snapshot_status` (`written` or `failed`)
  - `snapshot_dir`, `snapshot_error`

9. `POST /tasks/{task_id}/actions/gen-cv`
- Task action endpoint (currently for `gen_cv`).
- Request fields:
  - `profile_id`
  - `job` (object)
  - `candidate_profile` (object, `seniority` required)
  - `selected_claim_ids` (optional)
  - `llm_model` (optional)
  - `allow_mock_fallback` (optional, default `true`)
- Response fields:
  - `cv_markdown`
  - `generated_cv_json` (optional)
  - `model_info` (optional, includes `fallback_used`)

## 3) Error codes

- `404`: unknown task/profile or missing resources
- `422`: request validation, domain/config validation, or unsupported capability
- `500`: runtime failure in `/run` (notably when snapshot is required and cannot be written)
- `503`: generation provider/runtime failure in `gen-cv`

## 4) Sample requests

### 4.1 Prompt generation

```json
POST /v1/tasks/job_search/prompt/generate
{
  "profile_id": "profile_example",
  "step": "S3_execute"
}
```

### 4.2 JSONL validation

```json
POST /v1/tasks/job_search/jsonl/validate
{
  "profile_id": "profile_example",
  "raw_jsonl": "{\"id\":\"1\",\"source\":\"linkedin\",\"title\":\"Senior Engineer\",\"company\":\"Acme\",\"stack\":[\"python\"],\"modality\":\"remote\",\"seniority\":{\"level\":\"senior\"},\"apply_url\":\"https://acme.com/apply\",\"geo\":{\"region\":\"EU\"},\"evidence\":[],\"facts\":[],\"inferences\":[],\"anomalies\":[],\"incomplete\":false}\n"
}
```

### 4.3 Run scoring

```json
POST /v1/tasks/job_search/run
{
  "profile_id": "profile_example",
  "records": [
    {
      "id": "1",
      "source": "linkedin",
      "title": "Senior Engineer",
      "company": "Acme",
      "stack": ["python"],
      "modality": "remote",
      "seniority": {"level": "senior"},
      "apply_url": "https://acme.com/apply",
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
```

### 4.4 Run preflight validation

```json
POST /v1/tasks/job_search/run/validate
{
  "profile_id": "profile_example",
  "records": [],
  "require_snapshot": true
}
```

### 4.5 GEN_CV action

```json
POST /v1/tasks/gen_cv/actions/gen-cv
{
  "profile_id": "profile_example",
  "job": {
    "id": "job-1",
    "title": "Backend Engineer",
    "company": "Acme",
    "stack": ["python"]
  },
  "candidate_profile": {
    "id": "cand-1",
    "name": "Jane Doe",
    "seniority": "senior"
  },
  "allow_mock_fallback": true
}
```

## 5) Source of truth

- OpenAPI artifact: `docs/openapi_v1.json`
- Pydantic contracts: `src/structured_search/contracts.py`
