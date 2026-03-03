# ADR 0001 — Architecture Baseline

- **Status:** Accepted
- **Date:** 2026-03-02
- **Owners:** structured-search maintainers
- **Supersedes:** none
- **Superseded by:** none

## Context

`structured-search` serves two production-like local workflows (`job_search`, `gen_cv`) with strong needs for auditability, configurability, and fast iteration. The team needed a stable baseline for:

1. Layering and dependency direction.
2. Persistence strategy for profile/run artifacts.
3. Runtime behavior when the primary local LLM provider is unavailable.

This ADR records the three baseline decisions currently implemented in the codebase.

---

## Decision A — Use a Hexagonal Modular Monolith

### Decision

Adopt a hexagonal modular monolith:
- `domain/`: pure models and invariants.
- `ports/`: capability contracts (ABCs/Protocols).
- `infra/`: adapter implementations.
- `application/core/`: task plugin orchestration and use cases.
- `api/`: HTTP delivery and route wiring.

### Alternatives considered

1. **Layered monolith without explicit ports**
   - Pros: fewer files, lower upfront abstraction cost.
   - Cons: tighter coupling to concrete integrations, harder testability.
2. **Microservices split per task**
   - Pros: independent deployability and scaling.
   - Cons: operational overhead and premature distribution complexity.

### Tradeoffs

- Positive: strong test seams, easier adapter replacement, clearer boundaries.
- Negative: additional indirection and larger orchestration modules if not actively kept small.

### Consequences

- New external capabilities should be introduced as ports + adapters, not direct infra calls from domain.
- Dependency direction must remain inward (no domain imports from outer layers).

---

## Decision B — Use Filesystem-first Persistence (No DB yet)

### Decision

Persist operational state on filesystem:
- Profiles/bundles in `config/{task_id}/{profile}/bundle.json`.
- Atoms in YAML under `config/{task_id}/{profile}/atoms/`.
- Run snapshots in `runs/{run_id}/`.

No relational/document database is introduced at this stage.

### Alternatives considered

1. **PostgreSQL as primary persistence now**
   - Pros: transactional semantics, query flexibility.
   - Cons: setup/ops overhead and migration burden before requirements stabilize.
2. **KV/document store (e.g., Redis/Mongo)**
   - Pros: flexible shape persistence.
   - Cons: still adds infra complexity without current necessity.

### Tradeoffs

- Positive: very low setup cost, easy local reproducibility, transparent artifacts.
- Negative: weaker concurrency controls, coarse querying, manual retention lifecycle.

### Consequences

- Snapshot writes are best-effort unless explicitly required by API request.
- Migration path to DB remains open once throughput/concurrency requirements justify it.

---

## Decision C — Keep LLM Fallback Policy for Local Resiliency

### Decision

For `gen_cv`, primary provider is `OllamaLLM`; if unavailable or generation fails, fallback to `MockLLM` is allowed by default (`allow_mock_fallback=true`) to preserve local flow continuity.

### Alternatives considered

1. **Fail hard when LLM is unavailable**
   - Pros: strict correctness and early operational signal.
   - Cons: poor local DX, blocked UI flow when local Ollama is down.
2. **Use external hosted LLM fallback**
   - Pros: higher availability.
   - Cons: introduces cost/secrets/compliance/runtime variability.

### Tradeoffs

- Positive: resilient local workflow and deterministic fallback output for dev/testing.
- Negative: risk of masking provider outages if fallback ratio is not monitored.

### Consequences

- API must expose whether fallback was used (`model_info.fallback_used`).
- Observability must track fallback usage as an explicit metric (`gen_cv_fallback_used_ratio`).

---

## Validation / follow-up

- Keep these decisions linked from `docs/ARCHITECTURE.md` section 14.
- Revisit this ADR when any of these become false:
  - a database is introduced as source of truth,
  - service decomposition leaves monolith boundaries,
  - fallback policy changes from opt-out to strict fail-hard.
