# Examples Guide

This folder contains sanitized profiles and datasets for local testing.

## 1) What is included

- `examples/job_search/profile_example/`: baseline `job_search` profile + sample `job.json` and `candidate.json`
- `examples/gen_cv/profile_example/`: baseline `gen_cv` profile
- `examples/job_search/qa_*/`: QA-focused `job_search` profiles
- `examples/qa/data/*.jsonl`: synthetic datasets (`valid_batch`, `edge_cases`, `hostile`)
- `examples/qa/scripts/`: smoke/API QA scripts

## 2) Use examples as profile source

Point runtime to `examples/`:

```bash
export PROFILES_BASE=examples
```

Then run commands normally.

## 3) Quick CLI checks

### 3.1 Prompt generation (`job_search`)

```bash
PROFILES_BASE=examples uv run structured-search task job_search prompt \
  --profile profile_example \
  --step S3_execute \
  --output /tmp/examples_prompt.md
```

### 3.2 Deterministic run (`job_search`)

```bash
PROFILES_BASE=examples uv run structured-search task job_search run \
  --profile profile_example \
  --input examples/qa/data/valid_batch.jsonl \
  --output /tmp/examples_scored.jsonl
```

### 3.3 CV generation (`gen_cv`)

```bash
python3 - << 'PY'
import json
from pathlib import Path

job = json.loads(Path('examples/job_search/profile_example/job.json').read_text(encoding='utf-8'))
candidate = json.loads(Path('examples/job_search/profile_example/candidate.json').read_text(encoding='utf-8'))
Path('/tmp/examples_gen_cv_request.json').write_text(
    json.dumps(
        {
            'profile_id': 'profile_example',
            'job': job,
            'candidate_profile': candidate,
            'allow_mock_fallback': True,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding='utf-8',
)
PY

PROFILES_BASE=examples uv run structured-search task gen_cv action \
  --name gen-cv \
  --request /tmp/examples_gen_cv_request.json
```

## 4) Start API/UI with examples

### 4.1 API only

```bash
PROFILES_BASE=examples uv run structured-search dev api --reload
```

or using Makefile:

```bash
PROFILES_BASE=examples make api-dev
```

### 4.2 API + UI

```bash
PROFILES_BASE=examples uv run structured-search dev all --reload
```

or using Makefile:

```bash
PROFILES_BASE=examples make dev
```

## 5) API sanity checks

With API running:

```bash
curl -s http://127.0.0.1:8000/v1/tasks/job_search/profiles
curl -s http://127.0.0.1:8000/v1/tasks/gen_cv/profiles
```

## 6) QA automation scripts

Run smoke checks (CLI):

```bash
bash examples/qa/scripts/smoke.sh
```

Run API contract checks (requires API up):

```bash
python3 examples/qa/scripts/api_checks.py
```

## 7) Optional: copy example profiles into `config/`

If you prefer not to set `PROFILES_BASE`, copy profiles to `config/`:

```bash
mkdir -p config/job_search config/gen_cv
cp -r examples/job_search/profile_example config/job_search/
cp -r examples/gen_cv/profile_example config/gen_cv/
```

Then you can run without `PROFILES_BASE=examples`.
