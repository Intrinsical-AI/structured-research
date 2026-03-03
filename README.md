# Structured Search with LLMs

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI 0.115+](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> Disclaimer: do not use this project in a production environment, only local usage. E.g: CORS setted open(`allow_origins=["*"]`).

Structured Search is a local-first framework for general **structured search workflows and tasks**.

It combines:

- non-deterministic structured extraction via LLMs
- deterministic strict schema validation
- deterministic post-processing (gates + scoring)

Supported tasks (custom):

- `job_search`: workflow with guardrails. Constrains + user + preferences. Exploring + soft ranking over extracted job postings.
- `gen_cv`: grounded CV generation using curated atoms with user background (`context`, `claim`, `evidence`)

## Why this exists

LLMs are strong for exploration, weak for repeatability.

This project separates concerns:

- upstream extraction can be probabilistic
- downstream validation/scoring is deterministic for the same input + config

That gives better traceability, safer iteration on prompts/config, and easier debugging.

## Quick Guide (5 minutes)

### 1) Install

```bash
uv sync
```

### 2) Start local API + UI

```bash
# one-time setup
uv run structured-search dev api-install
uv run structured-search dev ui-install

# run both services
uv run structured-search dev all --reload
```

### 3) Run a first prompt generation

```bash
uv run structured-search job-search prompt \
  --profile profile_1 \
  --step S3_execute
```

For further information about templates, check [docs/CONFIG_TASK.md](./docs/CONFIG_TASK.md).

For the full operational guide (end-to-end flows, JSONL run, GEN_CV, tools, API/UI mapping), use [docs/USAGE.md](./docs/USAGE.md).

## Documentation Map

- [docs/USAGE.md](./docs/USAGE.md): setup and day-to-day commands (CLI/API/UI).
- [docs/CONFIG_TASK.md](./docs/CONFIG_TASK.md): detailed explanation of config templates and `bundle.json` mapping.
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md): architecture spec, boundaries, invariants, decisions.
- [docs/API_CONTRACT_V1.md](./docs/API_CONTRACT_V1.md): HTTP contract details.
- [docs/openapi_v1.json](./docs/openapi_v1.json): generated OpenAPI artifact.
- [docs/TEST_SUITE_DESIGN.md](./docs/TEST_SUITE_DESIGN.md): test strategy and quality direction.

## Repository at a Glance

```text
src/structured_search/
  api/            # FastAPI delivery layer
  application/    # use-case orchestration
  contracts.py    # API/application DTOs
  domain/         # pure models and invariants
  infra/          # adapter implementations
  ports/          # interfaces/contracts
  tasks/          # task slices (job_search, gen_cv)
  tools/          # utility commands

config/
  job_search/     # profile bundles + atoms
  templates/      # config templates

resources/prompts/
  _base/
  job_search/
  gen_cv/
```

## License

[MIT](./LICENSE)
