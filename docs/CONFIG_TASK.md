# Task Configuration and Templates

Reference for profile bundles and JSON templates under `config/templates/`.

Templates available:
- `config/templates/constraints.template.json`
- `config/templates/task.template.json`
- `config/templates/task_config.template.json`
- `config/templates/user_profile.template.json`
- `config/templates/domain_schema.template.json`
- `config/templates/schema.template.json`

## 1) Runtime model

The runtime reads a single bundle file per task/profile:

- `config/{task_id}/{profile_id}/bundle.json`

Equivalent path if `PROFILES_BASE` is overridden:

- `{PROFILES_BASE}/{task_id}/{profile_id}/bundle.json`

The runtime does not read split files like `constraints.json` or `task.json` directly.

## 2) Required bundle shape

Minimum required top-level sections in `bundle.json`:
- `constraints` (object)
- `task` (object)
- `task_config` (object)

Optional sections:
- `user_profile` (object or `null`)
- `domain_schema` (object or `null`)
- `result_schema` (object or `null`)

Notes:
- `task_id` and `profile_id` may be present in file payload, but path params are the source of truth in API writes.
- Missing required sections fail bundle load/save validation.

## 3) Task-specific validation behavior

Validation is plugin-dependent.

### 3.1 Scoring tasks (`job_search`, `product_search`)

In addition to the required top-level sections:
- `constraints` must validate against task constraints model.
- `task` must include valid `gates` and `soft_scoring` payload.
- rule field paths are checked against the task record model.

Unknown field paths in rules are warnings, not hard errors.

### 3.2 Action-only task (`gen_cv`)

- `constraints` still uses base constraints model (must include `domain`).
- `task` can be `{}` (no scoring runtime validation).
- `task_config.runtime.llm.model` is used in model-resolution chain for CV generation.

## 4) Template-to-bundle mapping

| Template | Bundle field | Required | Used at runtime |
| --- | --- | --- | --- |
| `constraints.template.json` | `constraints` | yes | gating/scoring constraints, rule semantics |
| `task.template.json` | `task` | yes | `gates` and `soft_scoring` for scoring tasks |
| `task_config.template.json` | `task_config` | yes | runtime metadata; `runtime.llm.model` for `gen_cv` |
| `user_profile.template.json` | `user_profile` | no | prompt augmentation (`## Candidate Profile`) for prompt-capable tasks |
| `domain_schema.template.json` | `domain_schema` | no | metadata only (not consumed by scorer) |
| `schema.template.json` | `result_schema` | no | metadata only (external validation/docs tooling) |

Important: templates include placeholder/example fields and extra metadata. Not all keys are consumed by runtime logic.

## 5) Constraint rule semantics

Rules in `constraints.must`, `constraints.prefer`, `constraints.avoid` follow `ConstraintRule`:

- `field`: dotted path (example: `geo.region`)
- `op`: one of `=`, `in`, `contains_any`, `contains_all`, `>=`, `<=`, `<`, `>`, `weighted`
- `value`: payload for operator
- optional fields: `weight`, `weights`, `severity`, `neutral_if_na`, `reason`, `time_decay_half_life_days`

Validation examples:
- `weighted` requires `weights` and same length as `value`.
- list operators require list `value`.
- compare operators require numeric `value`.

## 6) Build a new profile bundle

### 6.1 Preferred: copy an existing working profile

Examples:

```bash
cp -r config/job_search/profile_example config/job_search/profile_new
cp -r config/product_search/profile_example config/product_search/profile_new
cp -r config/gen_cv/profile_example config/gen_cv/profile_new
```

Then edit `config/{task_id}/profile_new/bundle.json`.

### 6.2 From templates

Compose a single `bundle.json` manually by embedding template sections under:
- `constraints`
- `task`
- `task_config`
- optional sections

You can also scaffold a new task layout with:

```bash
uv run structured-search tools scaffold-task --task-id <new_task_id>
```

## 7) Minimal valid examples

### 7.1 Scoring task (`job_search` / `product_search`)

```json
{
  "profile_id": "profile_example",
  "constraints": {
    "domain": "job_search",
    "must": [],
    "prefer": [],
    "avoid": []
  },
  "task": {
    "gates": {
      "hard_filters_mode": "require_all",
      "hard_filters": [],
      "reject_anomalies": [],
      "required_evidence_fields": []
    },
    "soft_scoring": {
      "formula_version": "v2_soft_after_gates",
      "prefer_weight_default": 1.0,
      "avoid_penalty_default": 1.0,
      "signal_boost": {},
      "penalties": {}
    }
  },
  "task_config": {},
  "user_profile": null,
  "domain_schema": null,
  "result_schema": null
}
```

### 7.2 Action task (`gen_cv`)

```json
{
  "profile_id": "profile_example",
  "constraints": {
    "domain": "gen_cv",
    "must": [],
    "prefer": [],
    "avoid": []
  },
  "task": {},
  "task_config": {
    "runtime": {
      "llm": {
        "model": "lfm2.5-thinking"
      }
    }
  }
}
```

## 8) Save/validation behavior via API

`PUT /v1/tasks/{task_id}/profiles/{profile_id}/bundle` always returns HTTP `200` with:

- `ok: true` and optional warnings in `errors`
- `ok: false` with validation errors in `errors`

Common issues:
- missing `constraints`, `task`, or `task_config`
- invalid rule payloads (`weighted` without valid `weights`, etc.)
- invalid scoring runtime structure for scoring tasks (`gates`/`soft_scoring` missing)
- non-object `task_config`
- placeholder values not adapted to the real task schema
