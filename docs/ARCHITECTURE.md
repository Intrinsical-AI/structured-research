# structured-search — Architecture Spec

> **Owners:** structured-search maintainers
> **Scope:** Python backend (`domain`, `ports`, `infra`, `tasks`, `api`), filesystem config/profiles, prompt system, and API contracts consumed by UI / **Out of scope:** hosted production topology, external authN/authZ, distributed messaging, multi-node consistency

---

## 0) TL;DR (90 seconds)
**Status:** Current

- **What:** `structured-search` is a modular monolith for auditable LLM-assisted workflows. It currently implements two vertical tasks: `job_search` (structured ranking with gates + soft scoring) and `gen_cv` (grounded CV generation).
- **Why:** the system optimizes precision, traceability, reproducibility, and extensibility, with explicit evidence anchoring and configuration-driven behavior (`bundle.json` + atoms YAML), avoiding hidden runtime rules in code.
- **How:**
  - Pure domain models in `src/structured_search/domain/`.
  - Port contracts in `src/structured_search/ports/` define external capabilities.
  - Infrastructure adapters in `src/structured_search/infra/` implement those ports.
  - Task services in `src/structured_search/tasks/` orchestrate per-use-case flows.
  - HTTP layer in `src/structured_search/api/` exposes `/v1` endpoints.
  - Profiles (`config/job_search/{profile}`) drive runtime gates, scoring, and grounding.
  - Run snapshots in `runs/{run_id}` persist constraints/task/input/output/summary for replayability.
- **Non-negotiables:**
  - Domain layer does not depend on ports/infra/tasks/api.
  - Gates are evaluated before soft scoring.
  - Evidence and claim lineage must remain traceable.
  - Parsers/readers are tolerant where feasible (notably API ingest); some CLI paths intentionally fail fast on invalid input.
  - `bundle.json` is the source of runtime behavior for scoring and prompts.
  - API contract is versioned under `/v1` and documented in `docs/API_CONTRACT_V1.md`.

### Documentation split
- Operational commands and end-to-end workflows: `docs/USAGE.md`.
- Template semantics and bundle mapping: [../CONFIG_TASK.md](../CONFIG_TASK.md).
- Architectural rationale, boundaries, invariants, and decisions: this document.
- HTTP contract details: `docs/API_CONTRACT_V1.md` + generated `docs/openapi_v1.json`.

---

## 1) Goals, Non-goals, Constraints
**Status:** Current

### 1.1 Goals (prioritized)
1. Deliver deterministic, auditable ranking for structured `job_search`.
2. Deliver grounded CV generation (`gen_cv`) with claim/evidence traceability.
3. Keep architecture extensible through ports/adapters and task co-location.
4. Keep workflow reproducible via profile bundles + run snapshots.

### 1.2 Non-goals
- Distributed microservices decomposition.
- Message broker/event-driven architecture.
- Multi-tenant auth and role-based access control.
- Cloud-native ops stack (managed DB/queue/trace backend) as part of current codebase.

### 1.3 Constraints (hard)
- Legal / regulatory: no explicit framework-specific compliance module exists; prompts include security guardrails and evidence discipline.
- Budget / latency / throughput: local-first execution (filesystem + local Ollama by default), no formal SLO budget codified.
- Team: architecture rules are enforced by CI (`uv run structured-search quality arch-lint`) plus tests.
- Tech (languages, runtime, hosting):
  - Backend: Python 3.12+, FastAPI, Pydantic v2.
  - Frontend: Next.js/React in `ui/` (consumer of API contract).
  - Runtime storage: filesystem (`config/`, `runs/`, `results/`).

### 1.4 Quality attributes

| Attribute    | Target                    | Measured by                                    |
| ------------ | ------------------------- | ---------------------------------------------- |
| Latency p95  | Not formally defined      | Local manual checks / endpoint behavior        |
| Availability | Not formally defined      | Process uptime (no production SLO in repo)     |
| Consistency  | Single-process + FS write | Pydantic validation + tests + run snapshots    |
| Cost         | Local runtime cost        | Local machine resources (no billing telemetry) |

---

## 2) Domain model
**Status:** Current

### 2.1 Glossary (ubiquitous language)
- **Atom:** curated unit of knowledge (`ContextAtom`, `ClaimAtom`, `EvidenceAtom`).
- **Bundle:** `bundle.json` containing profile constraints + task runtime config.
- **Constraint:** rule in `must`, `prefer`, or `avoid`.
- **Evidence Anchor:** source quote + locator proving a field value.
- **Fact Record:** extracted observed value linked to evidence IDs.
- **Inference Record:** derived value with reason/confidence linked to evidence IDs.
- **Gate:** hard filter evaluated before scoring.
- **Soft Scoring:** weighted ranking logic after gate pass.
- **Grounding:** constraining LLM outputs to curated atoms/claim IDs.
- **Port:** abstract capability contract (ABC/Protocol).
- **Adapter:** concrete implementation of a port.
- **Profile:** runtime configuration directory (`profile_1`, `profile_2`, ...).
- **Relaxation:** ordered strategy to loosen constraints when needed.
- **Snapshot:** persisted run artifact set (`constraints.json`, `task.json`, `input.jsonl`, `output.jsonl`, `summary.json`).
- **Task:** vertical workflow package (`job_search`, `gen_cv`) with models/service/cli.

### 2.2 Bounded contexts

| Context | Responsibility | Owns data? | External deps | Public APIs |
| ------- | -------------- | ---------: | ------------- | ----------- |
| Job Search Scoring | Parse postings, apply gates, compute ranked scores | Yes (`JobPosting`, `ScoredJobPosting`) | JSONL input/output, profile bundle | CLI `structured-search job-search ...`, `/v1/job-search/*` |
| CV Generation | Build grounded prompt, call LLM, validate structured CV | Yes (`JobDescription`, `CandidateAtomsProfile`, `GeneratedCV`) | Ollama/LLM port, atoms YAML | CLI `structured-search gen-cv ...`, `/v1/gen-cv` |
| Profile & Run Persistence | Load/save bundles and run snapshots | Yes (filesystem JSON/JSONL files) | OS filesystem | Service dependencies in API/CLI |
| Prompt Composition | Build prompt layers from base/task/profile/step files | Yes (prompt assembly rules) | markdown prompt files | `PromptComposer`, prompt endpoints/CLI |
| HTTP Contract | Expose stable DTOs and error semantics for UI | Yes (`contracts.py` DTOs) | FastAPI | `/v1/*` |

### 2.3 Entities & value objects

#### Entity: `JobPosting`
- **Identity:** `id` from extracted record.
- **Lifecycle:** raw dict -> validated `JobPosting` -> scored `ScoredJobPosting`.
- **Invariants:** strict modality/seniority typing; required `apply_url` and `geo`.
- **Context:** Job Search Scoring.
- **Storage:** transient in memory, persisted as JSONL outputs/snapshots.

#### Entity: `GeneratedCV`
- **Identity:** `{job_id}__{candidate_id}`.
- **Lifecycle:** request payload -> grounded prompt -> `CVOutput` validation -> `GeneratedCV`.
- **Invariants:** summary/highlights required as meaningful output; `grounded_claim_ids` filtered to known claims.
- **Context:** CV Generation.
- **Storage:** response payload / CLI output JSON.

#### Entity: `ProfileBundle`
- **Identity:** `profile_id`.
- **Lifecycle:** load -> validate -> save.
- **Invariants:** must contain `constraints`, `task`, `task_config`.
- **Context:** Profile & Run Persistence.
- **Storage:** `config/job_search/{profile_id}/bundle.json`.

#### Entity: `RunSnapshot`
- **Identity:** `run_id` (`{profile}-{timestamp}-{short_uuid}`).
- **Lifecycle:** generated in `/run` -> written best-effort (`written` or `failed`).
- **Invariants:** when snapshot succeeds, constraints/task/input/output/summary files exist.
- **Context:** Profile & Run Persistence.
- **Storage:** `runs/{run_id}/`.

#### Value Object: `ConstraintRule`
- **Equality:** structural value equality of all fields.
- **Validation:** operator-specific payload checks (`weighted`, compare/list operators, etc.).

#### Value Object: `EvidenceAnchor`
- **Equality:** structural value equality (`id`, `field`, `quote`, `url`, `locator`, etc.).
- **Validation:** mandatory source URL + locator metadata.

#### Value Object: `ScoringBreakdown`
- **Equality:** structural score components.
- **Validation:** composed from deterministic scorer and clamped final score.

---

## 3) Data model
**Status:** Current

### 3.1 Storage overview
- Primary DB: none (filesystem-first architecture).
- Cache: none explicit.
- Search / vector index: none in backend core (ranking is deterministic rule-based; grounding uses atoms files).
- Files / blobs:
  - Profiles and bundles: `config/job_search/*`.
  - Atoms: YAML under profile directories.
  - Run snapshots: `runs/*`.
  - Results/artifacts: `results/*`.

### 3.2 Schemas
> Link to migrations / schema files.
- No DB migrations currently.
- Runtime config templates:
  - `config/templates/constraints.template.json`
  - `config/templates/task.template.json`
  - `config/templates/task_config.template.json`
  - `config/templates/user_profile.template.json`
  - `config/templates/domain_schema.template.json`
  - `config/templates/schema.template.json`
- API contract reference: `docs/API_CONTRACT_V1.md`.

### 3.3 DTOs / Contracts
- Canonical location: `src/structured_search/contracts.py`
- Versioning: path-based (`/v1`) with strict `snake_case` request fields.
- Exported HTTP contract artifact: `docs/openapi_v1.json` (generated via `structured-search tools export-openapi`).
- UI generated types artifact: `ui/lib/generated/api-types.ts` (generated via `structured-search tools export-ui-types`).

#### DTO: `RunScoreRequest`
- **Purpose:** request (`POST /v1/job-search/run`)
- **Fields:** `profile_id` (required), `records` (required), `require_snapshot` (optional).
- **Example:**

```json
{
  "profile_id": "profile_1",
  "records": [{ "id": "1", "company": "Acme", "title": "Engineer" }],
  "require_snapshot": false
}
```

#### DTO: `GenCVRequest`
- **Purpose:** request (`POST /v1/gen-cv`)
- **Fields:** `profile_id`, `job`, `candidate_profile`, optional `selected_claim_ids`, `llm_model`, `allow_mock_fallback`.
- **Rule:** `candidate_profile.seniority` is required by service-level validation.
- **Example:**

```json
{
  "profile_id": "profile_1",
  "job": { "id": "job-001", "title": "Senior Backend Engineer", "company": "Acme", "stack": ["Python"] },
  "candidate_profile": { "id": "cand-1", "seniority": "senior" },
  "allow_mock_fallback": true
}
```

### 3.4 Mapping rules (DTO <-> Domain <-> Persistence)
- DTO -> Domain:
  - API layer uses Pydantic DTOs, then service-level coercion/validation (`_job_input_to_description`, `_candidate_input_to_profile`).
  - `task_json_to_scoring_config` maps bundle `task` into runtime `SoftScoringConfig`.
  - Task mode aliases are normalized (`any` -> `require_any`, `all` -> `require_all`).
- Domain -> Persistence:
  - `FilesystemProfileRepository` persists bundle payloads as JSON.
  - `FilesystemRunRepository` persists snapshot files (`constraints`, `task`, input/output JSONL, summary).
- Forbidden shortcuts:
  - Domain models should not perform I/O.
  - Port boundaries should not be bypassed by embedding adapter behavior inside domain.

---

## 4) Invariants & validation
**Status:** Current

### 4.1 Global invariants
- Domain stays framework/I/O free.
- Gates run before soft scoring.
- Scored records with failed gates must have `score=None`.
- Atoms references must remain resolvable (`ClaimAtom.evidence_ids` -> existing evidence), validated by atoms validation tooling.
- `bundle.json` must contain `constraints`, `task`, and `task_config`.
- `/v1/gen-cv` rejects missing/empty `candidate_profile.seniority` with `422`.

### 4.2 Per-aggregate invariants

| Aggregate | Invariant | Enforced where | Test coverage |
| --------- | --------- | -------------- | ------------- |
| `ConstraintRule` / scorer | Operator payload validity and tri-state rule evaluation | `domain/models.py`, `infra/scoring.py` | `tests/unit_test_models.py`, `tests/unit_test_scorer.py` |
| `ProfileBundle` | Required sections + warning/error split on save | `application/job_search/profiles.py::save_bundle` | `tests/api_test_bundle.py`, `tests/unit_test_application_job_search.py` |
| Atoms graph | Context/claim/evidence referential integrity | `tools/validate_atoms.py` (load-time parsing in `infra/grounding.py`) | `tests/integration_test_grounding.py`, `tests/unit_test_scripts.py` |
| JSONL ingest | Recover valid records while collecting parser/schema errors | `infra/loading.py`, `application/job_search/ingest.py::ingest_validate_jsonl` | `tests/api_test_ingest.py`, `tests/unit_test_application_job_search.py` |
| `GeneratedCV` flow | Grounded claim IDs filtered to available claims | `tasks/gen_cv/service.py` | `tests/unit_test_gen_cv_service.py`, `tests/api_test_gen_cv.py` |

### 4.3 Failure semantics
- Validation errors:
  - `404` -> missing profile/resources (`FileNotFoundError`).
  - `422` -> request/domain validation (`ValidationError`, `ValueError`).
  - `500` -> run runtime failures (notably required snapshot write failure).
  - `503` -> CV provider/runtime unavailability.
- Idempotency:
  - `PUT /bundle` is effectively overwrite-idempotent for same payload.
  - `POST /run` is not idempotent in run identity (new `run_id` each call).
- Retry safety:
  - `/run` retries can produce multiple snapshots.
  - `/gen-cv` retries may produce different model outputs unless mocked.
- Consistency model per operation:
  - In-process strong consistency for single request execution.
  - Snapshot persistence can be best-effort unless `require_snapshot=true`.
- Special payload semantics:
  - `PUT /v1/job-search/profiles/{id}/bundle` always returns `200` with `ok=true|false`;
    validation issues are encoded in response payload, not HTTP status.

### 4.4 Scoring semantics
- Stage 1 (gates): `constraints.must` + `task.gates.hard_filters` + anomaly rejection + required evidence fields.
- Stage 2 (soft scoring), only if gates pass:
  - `base = 5.0`
  - `+ prefer boosts`
  - `- avoid penalties`
  - `+ signal boosts`
  - `- configured penalties`
  - final score is clamped to `[0, 10]`.
- Rule evaluation uses tri-state semantics:
  - `True`: rule satisfied
  - `False`: rule violated
  - `None`: neutral (`field missing` and `neutral_if_na=true`)
- Distinction is explicit between absent key (`_MISSING`) and explicit `null` (`None`):
  - `_MISSING` may be neutral based on rule config
  - `None` evaluates as failed for condition checks
- Supported operators: `=`, `in`, `contains_any`, `contains_all`, `>=`, `<=`, `<`, `>`, `weighted`.

---

## 5) Architecture style & layers
**Status:** Current

### 5.1 Style
- **Hexagonal modular monolith** with task-oriented vertical slices.
- Rationale:
  - Keep domain rules portable and testable.
  - Allow adapter swapping (loader/exporter/LLM/grounding/persistence).
  - Encapsulate workflow-specific logic by task package.
- Tradeoffs:
  - Application layer centralizes orchestration and must stay granular by use-case to avoid a new “God Service”.
- Layering contracts are explicit and CI-blocking (`.importlinter` + `structured-search quality arch-lint`).

### 5.2 Layers

| Layer | Responsibilities | Must NOT contain |
| ----- | ---------------- | ---------------- |
| Domain | entities/value objects, constraints, scoring/result models | HTTP, filesystem I/O, adapter wiring |
| Application | use-case orchestration (`application/common`, `application/job_search`, `application/gen_cv`) | low-level transport/framework details in core logic |
| Adapters | JSONL/YAML/filesystem/LLM prompt composition and persistence | domain policy decisions unrelated to external integration |
| Delivery | FastAPI routes (`api/app.py`) as thin controllers + CLI commands (`tasks/*/cli.py`) + UI client | deep business logic duplication |

### 5.3 Dependency rules
```
Domain       -> (nothing)
Application  -> Domain + Ports
Adapters     -> Domain + Ports
UI / API     -> Application
```

Rule: no upward imports; no circular dependencies.
Current enforcement: `import-linter` contracts + code review + tests.

Allowed (enforced):
- `ports` -> `domain`
- `infra` -> `domain` + `ports`
- `tasks` -> `domain` + `ports` (+ `infra` for composition)
- `api` -> service/use-cases and adapter wiring

Forbidden (enforced):
- `domain` importing any outer layer
- `ports` importing `infra`, `tasks`, or `api`
- `infra` importing `tasks` or `api`
- `tasks` importing `api` or sibling task packages

---

## 6) Components & interactions
**Status:** Current

### 6.1 Component diagram
> No standalone `docs/diagrams/components.[png|svg|mmd]` file exists yet; this section is the canonical textual diagram.

- **Domain models:** canonical business objects (`BaseResult`, `ConstraintRule`, atoms, scored types).
- **Ports:** contracts (`ScoringPort`, `LoadingPort`, `ExportingPort`, `LLMPort`, `GroundingPort`, `PromptComposerPort`, persistence ports, `BaseETLService`).
- **Infra adapters:** deterministic scorer, tolerant JSONL parser/loader, exporter, Ollama+Mock LLM, atoms grounding, prompt composer, filesystem repositories.
- **Prompt composition details:** base sections are `_base/01_identity.md`, `02_evidence.md`, `03_security.md`, `04_guardrails.md`; composition order is base -> task context -> profile context -> step, joined by `────` separators.
- **Tasks:** `ETLJobSearch` and `GenCVService`.
- **API:** FastAPI router + service orchestration + DTO mapping.

### 6.2 Main flows

#### Flow: `Job Search ETL`
- Trigger: CLI `structured-search job-search run` or `POST /v1/job-search/run`.
- Steps:
  - Load constraints/task config from profile bundle.
  - Parse/validate input records as `JobPosting`.
  - Apply stage-1 gates; if pass, apply stage-2 soft scoring.
  - Emit scored records and summary metrics.
  - Persist snapshot files when run path uses snapshot repository.
- Side effects: JSONL outputs and run snapshot directory.
- Failure modes: schema validation skips, invalid task config -> `422`, snapshot write failure -> warning or `500` when required.

#### Flow: `CV Generation`
- Trigger: CLI `structured-search gen-cv run` or `POST /v1/gen-cv`.
- Steps:
  - Validate job/candidate payloads.
  - Grounding behavior by entrypoint:
    - API/application path: use atoms dir when present, otherwise `_EmptyGrounding` fallback.
    - Task CLI path: requires a valid atoms directory and fails fast when missing.
  - Rank contexts by stack overlap, expand claims/evidence, compose grounded prompt.
  - LLM behavior by entrypoint:
    - API/application path: try `OllamaLLM`, then optional `MockLLM` fallback (`allow_mock_fallback`).
    - Task CLI path: uses `OllamaLLM` directly; no mock fallback path.
  - Inside `OllamaLLM`, runtime path is: LangChain structured output -> direct HTTP fallback -> raw JSON extraction fallback (regex when needed) -> model-not-found hint (`ollama pull <model>`).
  - Validate `CVOutput`, filter cited claims, produce `GeneratedCV` + markdown.
- Side effects: optional output file in CLI mode.
- Failure modes: profile missing (`404`), payload/domain validation (`422`), LLM/runtime failure (`503`).

#### Flow: `Prompt Generation`
- Trigger: CLI `structured-search job-search prompt` or `POST /v1/job-search/prompt/generate`.
- Steps:
  - Compose prompt layers: base -> task context -> profile context -> step.
  - Embed constraints JSON.
  - API/application prompt path also embeds candidate profile (`user_profile`) when present in bundle.
  - Return prompt + hash metadata (HTTP path).
- Side effects: optional prompt file in CLI.
- Failure modes: missing profile/prompts directory.

#### Flow: `Run Preflight Validation (dry-run)`
- Trigger: CLI `structured-search job-search run-validate` or `POST /v1/job-search/run/validate`.
- Steps:
  - Load profile bundle and task configuration.
  - Parse and validate records exactly as `/run` would do.
  - Compute validation summary and gate readiness without writing scored outputs.
- Side effects: temporary snapshot I/O probe (write + cleanup) used to verify writability.
- Failure modes: profile/config missing (`404`), request/domain validation (`422`).

---

## 7) Interfaces: APIs, events, commands
**Status:** Current

### 7.1 Public API
- Protocol: REST (`/v1`) + CLI entrypoints.
- Auth: none implemented.
- Rate limiting: none implemented.

HTTP endpoints currently exposed:
- `GET /v1/job-search/profiles`
- `GET /v1/job-search/profiles/{profile_id}/bundle`
- `PUT /v1/job-search/profiles/{profile_id}/bundle`
- `POST /v1/job-search/prompt/generate`
- `POST /v1/job-search/jsonl/validate`
- `POST /v1/job-search/run/validate`
- `POST /v1/job-search/run`
- `POST /v1/gen-cv`

CLI entrypoint:
- `structured-search`

### 7.2 Events & messaging
- Broker: none.
- Topics: none.
- Delivery: synchronous request/response only.
- Consumer idempotency: not applicable (no brokered consumers).

---

## 8) Security, privacy, compliance
**Status:** Current

- Threat model:
  - Prompt-injection and malformed data in LLM-assisted extraction/generation paths.
  - Corrupt JSONL/YAML inputs from external/manual sources.
- Secrets management:
  - Environment variables (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `STRUCTURED_SEARCH_LLM_MODEL`, `PROFILES_BASE`).
  - No in-repo secret manager abstraction.
- PII handling:
  - Candidate/job payloads may contain personal/professional data; no dedicated PII policy module yet.
- Log redaction:
  - Standard Python logging is used; explicit redaction pipeline is not implemented.
- Supply-chain:
  - Python deps in `pyproject.toml` + `uv.lock`.
  - Frontend deps in `ui/package-lock.json`.
  - No SBOM generation pipeline currently in repo.

---

## 9) Performance, scalability, capacity
**Status:** Current

- Workload assumptions:
  - Local development and medium batch JSONL processing.
  - Single-process API and CLI execution.
- Known bottlenecks:
  - LLM roundtrips dominate CV generation latency.
  - Filesystem I/O for snapshots and profile loading.
  - Large API service orchestration surface can increase change risk.
- Benchmarks:
  - No formal benchmark suite codified in repo.
  - Typical validation command: `uv run structured-search quality test --quick`.
- Scaling strategy:
  - Current: vertical/local scaling.
  - Future: can split adapters/use-cases due to current modular boundaries.

---

## 10) Observability
**Status:** Partial

- Logs:
  - Module-level `logging` across API/services/adapters.
  - Warnings emitted for recoverable parsing/config/runtime issues.
- Metrics (golden signals):
  - No centralized metrics backend instrumentation.
  - Minimal metric event sink exists (`runs/metrics_q2_events.jsonl`) and is emitted from API flows.
  - `/run` returns per-request processing metrics in payload.
- Tracing:
  - Not implemented.
- Alerting thresholds:
  - Not implemented in repo.

### 10.1 Q2 baseline metrics (initial targets)
**Status:** Planned

| Metric | Definition | Initial Q2 target | Measured by | Notes |
| ------ | ---------- | ----------------- | ----------- | ----- |
| `run_latency_p95_ms` | p95 of end-to-end latency for `POST /v1/job-search/run` | `<= 1500 ms` for batches up to 100 records | `finished_at - started_at` from `/run` response metrics | Measure in controlled dev environment; publish weekly trend. |
| `snapshot_failed_rate` | `failed_snapshots / total_runs` for `/run` | `< 1%` | `snapshot_status` field in `/run` response (`written`/`failed`) | Track separately when `require_snapshot=true` vs `false`. |
| `jsonl_parse_error_ratio` | `parse_errors / total_lines` during JSONL validate | `< 15%` monthly median | `/v1/job-search/jsonl/validate` metrics (`parse_errors`, `total_lines`) | Proxy for extraction/prompt quality and input hygiene. |
| `gen_cv_fallback_used_ratio` | `fallback_used=true responses / total gen-cv responses` | `< 20%` in environments expecting local Ollama | `model_info.fallback_used` in `/v1/gen-cv` response | High ratio indicates LLM provider availability/config regressions. |

---

## 11) Testing strategy
**Status:** Current

| Type | Scope | Tools | Required gates |
| ---- | ----- | ----- | -------------- |
| Unit | domain/scorer/services/adapters/tools | `pytest` | `uv run structured-search quality test --quick` should pass |
| Integration | real atoms/config/filesystem behavior | `pytest` + `@pytest.mark.integration` | run in local test suite; no separate CI gate file currently |
| API contract | HTTP handlers/routes and DTO mappings | `pytest`, `fastapi.testclient` | route behavior and status mapping verified by tests |
| E2E | full system | Not currently implemented | N/A |
| Property | invariants | Not currently implemented | N/A |
| UI component tests | tab-level contract behavior | `vitest`, Testing Library | `cd ui && npm run test` (manual gate) |

Notes:
- `docs/TEST_SUITE_DESIGN.md` defines target strategy and stricter future thresholds.
- Current repository includes `.github/workflows/quality.yml` with blocking quality checks.

---

## 12) Deployment & environments
**Status:** Current

- Environments: `dev` is explicitly supported; `staging/prod` are not codified in repository infra.
- Config strategy: 12-factor style env vars where needed (`PROFILES_BASE`, `OLLAMA_*`, `STRUCTURED_SEARCH_LLM_MODEL`).
- Migrations: N/A (filesystem persistence, no DB schema migrations).
- Rollback plan:
  - Code rollback via VCS revert.
  - Config rollback via profile bundle history in VCS only for tracked profiles; local ignored profiles (for example `config/job_search/profile_1`, `profile_2`) require local backup/restore strategy.
  - Run artifacts are append-only per `run_id`; failures tracked via `snapshot_status`.

---

## 13) Repo layout & conventions
**Status:** Current

```text
src/structured_search/
  domain/
  ports/
  infra/
  tasks/
    job_search/
    gen_cv/
  api/
config/
  job_search/
  templates/
resources/
  prompts/
tests/
ui/
docs/
  ARCHITECTURE.md
  API_CONTRACT_V1.md
  TEST_SUITE_DESIGN.md
  adr/
    0001-architecture-baseline.md
```

- Naming:
  - Tasks are snake_case package names (`job_search`, `gen_cv`).
  - Profiles use `profile_*` convention.
- Error handling:
  - Parse/validation issues prefer typed accumulation where appropriate.
  - API maps typed exceptions to HTTP status boundaries.
- Code style:
  - `ruff` lint/format.
  - `pre-commit` config exists (`ruff`, basic hooks).

---

## 14) Architecture decisions (ADRs)
**Status:** Current

Current ADR baseline:
- `docs/adr/0001-architecture-baseline.md` captures 3 accepted baseline decisions:
  1. Hexagonal modular monolith architecture.
  2. Filesystem-first persistence for profiles/runs.
  3. LLM fallback policy (`OllamaLLM` -> `MockLLM`) for local resiliency.

Required ADR template for future decisions:
- Context and decision statement.
- Alternatives considered.
- Tradeoffs and consequences.
- Migration plan (if breaking).
- Validation/test impact.

---

## 15) Notes for new developers
**Status:** Current

- For local setup, CLI/API/UI workflows, and quality commands, use `docs/USAGE.md`.
- Keep this document focused on architecture constraints, invariants, and decisions.
- Where to add a new feature:
  - New task:
    1. `uv run structured-search tools scaffold-task --name <task_name>`
    2. Implement models/service/cli under `src/structured_search/tasks/<task_name>/`
    3. Add `config/<task_name>/<profile>/bundle.json` + `atoms/`
    4. Add prompt files in `resources/prompts/<task_name>/`
    5. Add/extend subcommands under `structured_search.cli` when needed
    6. Add unit/integration/API tests
  - New adapter:
    1. Define/extend the target port in `ports/` if needed
    2. Implement adapter in `infra/`
    3. Add mock adapter for tests
    4. Wire in `application/*` composition/use-case layer
- Common architecture pitfalls:
  - Drifting contract between `docs/API_CONTRACT_V1.md`, `contracts.py`, and UI types.
  - Adding logic directly into routes instead of service/use-case layer.
  - Breaking layer boundaries with convenience imports.
  - Forgetting that `/run` can succeed with failed snapshot when `require_snapshot=false`.
