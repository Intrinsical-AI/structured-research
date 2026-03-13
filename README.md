# structured-search

`structured-search` is a local-first framework for task-scoped, auditable LLM workflows.

## Quickstart

```bash
uv sync
uv run structured-search tasks list
uv run structured-search task job_search prompt \
  --profile-id profile_example \
  --step S3_execute \
  --output /tmp/job_search_prompt.md
uv run structured-search task job_search run \
  --profile-id profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/jobs_scored.jsonl
uv run structured-search task job_search run-validate \
  --request examples/job_search/run_request_example.json
uv run structured-search task gen_cv action \
  --action-name gen-cv \
  --request examples/gen_cv/request_example.json
```

## Built-in Tasks

| Task ID | Main capabilities |
| --- | --- |
| `job_search` | `prompt`, `jsonl_validate`, `run` |
| `product_search` | `prompt`, `jsonl_validate`, `run` |
| `gen_cv` | `action:gen-cv` |

## Runtime Layout

- Runtime profiles live under `config/{task_id}/{profile_id}/bundle.json`.
- The canonical demo profile name is `profile_example`.
- `examples/` contains payloads, datasets and QA scripts; it is not the runtime source of truth.
- `PROFILES_BASE` remains available as an optional override for custom deployments.

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

## Developer Commands

```bash
uv run structured-search dev api --reload
uv run structured-search dev all --reload
uv run structured-search quality lint
uv run structured-search quality test --quick
uv run structured-search tools validate-atoms
```

## Documentation

- [docs/USAGE.md](./docs/USAGE.md): setup and operational commands
- [docs/API_CONTRACT_V1.md](./docs/API_CONTRACT_V1.md): HTTP contract
- [docs/CONFIG_TASK.md](./docs/CONFIG_TASK.md): profile bundle structure
- [examples/README.md](./examples/README.md): example payloads and QA assets
