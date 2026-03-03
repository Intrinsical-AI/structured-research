# structured-search — Architecture Spec

> Owners: structured-search maintainers  
> Scope: Python backend (`domain`, `ports`, `infra`, `application`, `api`), filesystem profiles/runs, prompt system, and HTTP contract consumed by UI

---

## 0) TL;DR

`structured-search` is a **hexagonal modular monolith** for auditable LLM-assisted workflows.

Built-in tasks:
- `job_search`: deterministic gate + score pipeline
- `product_search`: deterministic gate + score pipeline
- `gen_cv`: grounded CV generation action

Core properties:
- business rules in domain/application layers
- external concerns behind ports/adapters (filesystem, prompts, LLM, grounding)
- runtime behavior driven by profile bundles (`config/{task_id}/{profile_id}/bundle.json`)
- replayability via run snapshots in `runs/{run_id}/`

---

## 1) Goals, Non-goals, Constraints

### 1.1 Goals
1. Deterministic, auditable scoring for run-capable tasks.
2. Grounded CV generation with explicit claim lineage and fallback behavior.
3. Extensible task model through plugin registration and capabilities.
4. Reproducibility via config bundles and snapshot artifacts.

### 1.2 Non-goals
- Microservices decomposition.
- Broker-based/event-driven orchestration.
- In-repo authN/authZ and multi-tenant platform concerns.
- Managed cloud deployment topology.

### 1.3 Hard constraints
- Python 3.12+, Pydantic v2.
- Filesystem-first persistence (no DB migrations in repo).
- Layer boundaries enforced with `import-linter`.
- `/v1` HTTP contract is versioned and published via OpenAPI export.

---

## 2) Runtime model

### 2.1 Task plugin model

Each task is declared as a `TaskPlugin` (`application/core/task_plugin.py`) with:
- `task_id`, `name`, `prompt_namespace`
- `capabilities`
- optional `constraints_model`, `record_model`, `task_runtime_model`
- optional `build_runtime` (for scoring tasks)
- optional `action_handlers`

Registered plugins (`application/core/task_registry.py`):
- `job_search`
- `product_search`
- `gen_cv`

### 2.2 Capability matrix

| Capability | job_search | product_search | gen_cv |
| --- | --- | --- | --- |
| `prompt` | yes | yes | no |
| `jsonl_validate` | yes | yes | no |
| `run` | yes | yes | no |
| `action:gen-cv` | no | no | yes |

Unsupported capability requests return `422`.

### 2.3 Profile bundle model

Bundle payload shape (`contracts.ProfileBundle`):
- required: `constraints`, `task`, `task_config`
- optional: `user_profile`, `domain_schema`, `result_schema`

Bundle validation behavior (`bundle_service.save_bundle`):
- hard errors -> `valid=false`, not persisted
- warnings (for example unknown field paths in rules) -> persisted with issues list

`PUT /bundle` always returns HTTP `200` with `ok=true|false` in body.

### 2.4 Run snapshot model

Run ID format (`run_service._make_run_id`):
- `{task_id}-{profile_id}-{YYYYMMDD-HHMMSS}-{short_uuid}`

Persisted files when snapshot write succeeds:
- `constraints.json`
- `task.json`
- `input.jsonl`
- `output.jsonl`
- `summary.json`

When snapshot write fails:
- response includes `snapshot_status="failed"`
- `/run` still succeeds unless `require_snapshot=true`

---

## 3) Architecture style and layers

### 3.1 Layer responsibilities

- `domain/`: entities/value objects/invariants (framework-agnostic)
- `ports/`: abstract contracts for external capabilities
- `infra/`: adapter implementations (filesystem, prompt composition, LLM, parser, scorer)
- `application/`: use-case orchestration (`bundle`, `prompt`, `ingest`, `run`, `gen_cv`)
- `api/`: FastAPI HTTP delivery layer (thin mapping)
- `cli.py`: task-scoped command-line delivery layer

### 3.2 Enforced dependency boundaries (`.importlinter`)

- `domain` cannot import `ports`, `infra`, `application`, `api`
- `ports` cannot import `infra`, `application`, `api`
- `infra` cannot import `api`
- `application` cannot import `api`
- `api.app` cannot import `infra`, `domain`, `ports` directly

---

## 4) Main components

### 4.1 Application services

- `bundle_service.py`: list/load/save bundles
- `prompt_service.py`: compose prompt + embed constraints/profile sections
- `ingest_service.py`: tolerant JSONL parse + record schema validation
- `run_service.py`: run scoring pipeline + snapshot + preflight validation
- `gen_cv/generate_cv.py`: CV action orchestration with LLM fallback policy

### 4.2 Infrastructure adapters

- `infra/persistence_fs.py`: profile + snapshot repositories
- `infra/prompts.py`: prompt composer (`_base` + task context + optional profile context + step)
- `infra/loading.py`: tolerant JSONL parser (single-line + multiline recovery)
- `infra/scoring.py`: deterministic two-stage scorer
- `infra/llm.py`: `OllamaLLM` with structured/raw JSON fallbacks + `MockLLM`
- `infra/grounding.py`: atoms-backed grounding for claims/evidence

### 4.3 API surface (`/v1`)

- `GET /tasks`
- `GET /tasks/{task_id}/profiles`
- `GET|PUT /tasks/{task_id}/profiles/{profile_id}/bundle`
- `POST /tasks/{task_id}/prompt/generate`
- `POST /tasks/{task_id}/jsonl/validate`
- `POST /tasks/{task_id}/run/validate`
- `POST /tasks/{task_id}/run`
- `POST /tasks/{task_id}/actions/gen-cv`

---

## 5) Core execution flows

### 5.1 Prompt generation (`prompt_service.generate_prompt`)

Trigger:
- CLI `structured-search task <task_id> prompt`
- API `POST /v1/tasks/{task_id}/prompt/generate`

Flow:
1. Load profile bundle.
2. Compose prompt sections:
   - `_base/*.md`
   - `{task}/context.md`
   - optional `{task}/profiles/{profile}/context.md`
   - `{task}/steps/{step}*.md`
3. Append `## Search Constraints` JSON block.
4. Append `## Candidate Profile` for plugins with `include_user_profile_in_prompt=True`.

### 5.2 JSONL validation (`ingest_service.ingest_validate_jsonl`)

Trigger:
- API `POST /v1/tasks/{task_id}/jsonl/validate`

Flow:
1. Parse tolerant JSONL (recover valid records, accumulate parse errors).
2. Validate each parsed record against task `record_model`.
3. Return `valid_records`, `invalid_records`, and metrics.

### 5.3 Deterministic run (`run_service.run_score`)

Trigger:
- CLI `structured-search task <task_id> run`
- API `POST /v1/tasks/{task_id}/run`

Flow:
1. Load bundle and build runtime (`constraints + scorer`) via plugin.
2. Validate incoming records with record schema.
3. For valid records:
   - stage 1: gates (`must`, hard filters, anomaly rejects, required evidence fields)
   - stage 2: soft scoring only if gate passed
4. Persist snapshot (`runs/{run_id}`) best-effort.
5. Return metrics + snapshot metadata.

### 5.4 Run preflight (`run_service.validate_run`)

Trigger:
- CLI `structured-search task <task_id> run-validate`
- API `POST /v1/tasks/{task_id}/run/validate`

Flow:
1. Load/validate bundle and runtime.
2. Validate all records as in `/run`.
3. Probe snapshot I/O (write + cleanup of temporary `_validate-*` directory).
4. Return `ok` and checks.

### 5.5 CV generation action (`gen_cv.generate_cv`)

Trigger:
- CLI `structured-search task gen_cv action --name gen-cv`
- API `POST /v1/tasks/gen_cv/actions/gen-cv`

Flow:
1. Validate/coerce `job` and `candidate_profile` (`seniority` required).
2. Resolve grounding (`AtomsGrounding` when atoms directory exists, otherwise empty grounding).
3. Resolve model name from request/env/task_config.
4. Attempt Ollama generation.
5. If generation is unavailable/fails and `allow_mock_fallback=true`, retry with deterministic `MockLLM`.
6. Validate CV output, filter claim IDs, return markdown + JSON + model info.

---

## 6) Deterministic scoring semantics

Implemented by `infra.scoring.HeuristicScorer`.

Stage 1 (gates):
- `constraints.must`: all failing rules block gate
- `task.gates.hard_filters` with mode:
  - `require_all`: every hard filter must pass
  - `require_any`: at least one must pass
- `task.gates.reject_anomalies`
- `task.gates.required_evidence_fields`

Stage 2 (soft scoring, only if gate passes):
- `base = 5.0`
- add prefer boosts
- subtract avoid penalties
- add configured signal boosts
- subtract configured penalties
- clamp final score to `[0, 10]`

Rule evaluation is tri-state:
- `True`: satisfied
- `False`: violated
- `None`: neutral (for missing/null with `neutral_if_na=true`)

If gate fails:
- `score = null`
- `score_breakdown = null`

---

## 7) Error and status semantics

### 7.1 API mapping

- `404`: unknown task/profile/missing resources
- `422`: unsupported capability, request validation, or domain/config validation errors
- `500`: `/run` runtime failure (for example required snapshot cannot be persisted)
- `503`: `gen-cv` provider/runtime failure

### 7.2 Idempotency

- `PUT /bundle`: overwrite-idempotent for same payload
- `POST /run`: non-idempotent run identity (`run_id` always new)
- `POST /actions/gen-cv`: model output may vary unless fallback/mocked

---

## 8) Storage model

No primary database. Filesystem-backed runtime state:
- profiles/bundles: `config/{task_id}/{profile_id}/bundle.json`
- optional atoms: `config/{task_id}/{profile_id}/atoms/`
- snapshots: `runs/{run_id}/`
- examples/fixtures/results: under `examples/` and `runs/`/`results/` as generated artifacts

---

## 9) Observability

- Logging: standard Python logging in API/services/adapters.
- Request-level metrics in `/run` responses.
- Event sink: `runs/metrics_q2_events.jsonl` via `emit_q2_metric_event`.
- Metrics helper commands:
  - `structured-search metrics report`
  - `structured-search metrics populate`
- Tracing/alerting stack: not implemented.

---

## 10) Testing and quality gates

Backend commands:

```bash
uv run structured-search quality lint
uv run structured-search quality format
uv run structured-search quality test --quick
uv run structured-search quality arch-lint
```

Coverage includes:
- unit tests for domain/scoring/services/adapters
- integration tests for grounding/config I/O
- API behavior/status mapping tests
- import boundary tests (`import-linter`)

UI has separate tests under `ui/` (`vitest`).

---

## 11) Repo layout (current)

```text
src/structured_search/
  api/
  application/
    common/
    core/
      plugins/
    gen_cv/
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

docs/
  ARCHITECTURE.md
  API_CONTRACT_V1.md
  USAGE.md
  CONFIG_TASK.md
  openapi_v1.json
```

---

## 12) Related docs

- Usage and operational commands: `docs/USAGE.md`
- API request/response contract: `docs/API_CONTRACT_V1.md`
- Bundle template semantics: `docs/CONFIG_TASK.md`
- ADR baseline: `docs/adr/0001-architecture-baseline.md`
