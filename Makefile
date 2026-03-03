.PHONY: install setup test lint arch-lint format clean metrics-q2 metrics-q2-populate \
        api-contract-export \
        ui-types-export \
        contract-sync \
        job-search-prompt job-search-run job-search-run-validate gen-cv \
        check-api-prereqs check-ui-prereqs check-dev-prereqs \
        api-install ui-install api-dev ui-dev dev

API_HOST ?= 127.0.0.1
API_PORT ?= 8000
UI_PORT ?= 3000
API_BASE ?= http://$(API_HOST):$(API_PORT)/v1
METRICS_PROFILE ?= profile_1
UV_CACHE_DIR ?= /tmp/uv_cache
export UV_CACHE_DIR

# ── Dev ───────────────────────────────────────────────────────────────────────

install:
	uv sync

setup: install
	uv run pre-commit install

test:
	uv run structured-search quality test

lint:
	uv run structured-search quality lint

arch-lint:
	uv run structured-search quality arch-lint

format:
	uv run structured-search quality format

metrics-q2:
	uv run structured-search metrics report

metrics-q2-populate:
	uv run structured-search metrics populate \
		--api-base $(API_BASE) \
		--profile-id $(METRICS_PROFILE)

api-contract-export:
	uv run structured-search tools export-openapi --output docs/openapi_v1.json

ui-types-export:
	uv run structured-search tools export-ui-types \
		--openapi docs/openapi_v1.json \
		--output ui/lib/generated/api-types.ts

contract-sync: api-contract-export ui-types-export

clean:
	uv run structured-search clean

# ── Local API + UI (functional mode) ─────────────────────────────────────────
#
#   Usage:
#     make api-install                 # install backend API extra deps
#     make ui-install                  # install UI deps once
#     make api-dev                     # backend only
#     make ui-dev                      # ui only (wired to local backend URL)
#     make dev                         # backend + ui with safe cleanup
#     make dev API_PORT=8010 UI_PORT=3001

check-api-prereqs:
	@command -v uv >/dev/null || (echo "uv no está instalado"; exit 1)
	@uv run python -c "import uvicorn" || \
		(echo ""; \
		echo "Prereq API fallido: no se pudo importar uvicorn."; \
		echo "Accion: uv run structured-search dev api-install"; \
		echo "Tip: si ves error de permisos de cache, usa UV_CACHE_DIR=/tmp/uv_cache"; \
		exit 1)
	@uv run python -c "import langchain_ollama" >/dev/null 2>&1 || \
		(echo "Aviso: CV con LLM real requiere langchain-ollama. Ejecuta: uv run structured-search dev api-install")

check-ui-prereqs:
	@command -v npm >/dev/null || (echo "npm no está instalado"; exit 1)
	@[ -f ui/package.json ] || (echo "No existe ui/package.json"; exit 1)
	@[ -d ui/node_modules ] || \
		(echo "Faltan dependencias de UI. Ejecuta: uv run structured-search dev ui-install"; exit 1)

check-dev-prereqs: check-api-prereqs check-ui-prereqs

api-install:
	uv run structured-search dev api-install --uv-cache-dir $(UV_CACHE_DIR)

ui-install:
	uv run structured-search dev ui-install --ui-dir ui

api-dev: check-api-prereqs
	uv run structured-search dev api \
		--host $(API_HOST) \
		--port $(API_PORT) \
		--reload

ui-dev: check-ui-prereqs
	uv run structured-search dev ui \
		--ui-dir ui \
		--api-base "$(API_BASE)" \
		--ui-port $(UI_PORT)

dev: check-dev-prereqs
	uv run structured-search dev all \
		--host $(API_HOST) \
		--port $(API_PORT) \
		--reload \
		--ui-dir ui \
		--ui-port $(UI_PORT) \
		--api-base "$(API_BASE)"

# ── Job Search — two-phase workflow ──────────────────────────────────────────
#
#   Phase 1: generate prompt → paste into web UI → save JSONL response
#   Phase 2: validate, score, and export the JSONL
#
#   PROFILE: name of directory under config/job_search/ (default: profile_1)
#
#   Usage:
#     make job-search-prompt                                   # stdout, profile_1
#     make job-search-prompt PROFILE=profile_1                # different profile
#     make job-search-prompt OUTPUT=prompt.md                 # to file
#     make job-search-run INPUT=raw.jsonl                     # profile_1
#     make job-search-run INPUT=raw.jsonl PROFILE=profile_1   # different profile
#     make job-search-run-validate REQUEST=run_request.json   # dry-run preflight for /run

PROFILE ?= profile_1

job-search-prompt:
	uv run structured-search task job_search prompt \
		--profile $(PROFILE) \
		--step S3_execute \
		$(if $(OUTPUT),--output $(OUTPUT),)

job-search-run:
ifndef INPUT
	$(error INPUT is required: make job-search-run INPUT=raw.jsonl [OUTPUT=scored.jsonl] [PROFILE=profile_1])
endif
	uv run structured-search task job_search run \
		--profile $(PROFILE) \
		--input $(INPUT) \
		--output $(or $(OUTPUT),data/processed/jobs_scored.jsonl)

job-search-run-validate:
ifndef REQUEST
	$(error REQUEST is required: make job-search-run-validate REQUEST=run_request.json)
endif
	uv run structured-search task job_search run-validate \
		--request "$(REQUEST)"

# ── Gen CV ────────────────────────────────────────────────────────────────────
#
#   Requires a local Ollama instance.
#
#   Usage:
#     make gen-cv REQUEST=gen_cv_request.json
#     make gen-cv REQUEST=gen_cv_request.json OUTPUT=data/cvs/cv_response.json

gen-cv:
ifndef REQUEST
	$(error REQUEST is required: make gen-cv REQUEST=gen_cv_request.json [OUTPUT=data/cvs/cv_response.json])
endif
	uv run structured-search task gen_cv action \
		--name gen-cv \
		--request "$(REQUEST)" \
		> $(or $(OUTPUT),data/cvs/cv_response.json)
