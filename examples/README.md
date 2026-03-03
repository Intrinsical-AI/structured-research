# Guide & Mock Examples

This directory contains a safe, mock configuration that you can use to test the tools without exposing real Personal Identifiable Information (PII). 

## 1. Setup

An easy way to test the codebase is to set the `PROFILES_BASE` environment variable to point to this `examples/` directory for the backend, or literally copy the `profile_example` to the `config` folder.

**Option A: Test out-of-the-box using the environment variable**

```bash
export PROFILES_BASE=examples/job_search
make api
```

The UI will automatically pull the `profile_example` when loading!

**Option B: Copy to config (Local, gitignored)**

```bash
mkdir -p config/job_search
cp -r examples/job_search/profile_example config/job_search/
```

## 2. Generating Prompts

Generate a prompt using the test bundle constraints:

```bash
uv run structured-search-job-search prompt \
  --profile profile_example \
  --step S3_execute
```
*(If testing via Option A, don't forget `PROFILES_BASE=examples/job_search uv run...`)*

You can paste this prompt into your preferred LLM and save its output as `raw.jsonl`.

## 3. Extract & Score (Job Search)

Once you have your `raw.jsonl` from the LLM, validate and score it:

```bash
uv run structured-search-job-search run \
  --profile profile_example \
  --input data/test/raw.jsonl \
  --output data/test/scored.jsonl
```

## 4. CV Generation

The CV prompt was previously missing in `resources/prompts/gen_cv/01_identity.md`. It has now been created. 
You can render the full GEN_CV prompt (with atoms embedded) and export it to markdown:

```bash
uv run structured-search gen-cv prompt \
  --job examples/job_search/profile_example/job.json \
  --candidate examples/job_search/profile_example/candidate.json \
  --profile profile_example \
  --atoms-dir examples/job_search/profile_example/atoms \
  --output data/test/gen_cv_prompt.md
```

This also writes a base snapshot (`data/test/gen_cv_prompt.base.md`) to refine the base prompt.

You can generate a tailored CV for a local job JSON using the mocked candidate profile:

```bash
uv run structured-search gen-cv run \
  --job examples/job_search/profile_example/job.json \
  --candidate examples/job_search/profile_example/candidate.json \
  --profile profile_example \
  --llm-model lfm2.5-thinking \
  --atoms-dir examples/job_search/profile_example/atoms \
  --verbose
```

This will rank the "Grounded Facts" located inside the `atoms/` directory alongside the dummy candidate profile to export a targeted `cv.json`.
