# Task Configuration Templates

Reference guide for the JSON templates under `config/templates/`.
- `config/templates/constraints.template.json`
- `config/templates/task.template.json`
- `config/templates/task_config.template.json`
- `config/templates/user_profile.template.json`
- `config/templates/domain_schema.template.json`
- `config/templates/schema.template.json`

## 1) Runtime profile model

For each profile, the canonical runtime file is:

- `config/<task_name>/<profile_id>/bundle.json`

For current built-in flow, this is:

- `config/job_search/<profile_id>/bundle.json`

`bundle.json` must include:

- `constraints` (required)
- `task` (required)
- `task_config` (required)

Optional sections:

- `user_profile`
- `domain_schema`
- `result_schema`

## 2) Template-to-bundle mapping

| Template file | Bundle field | Required | Runtime usage |
|---|---|---|---|
| `constraints.template.json` | `constraints` | Yes | Used by scoring gates/soft rules and field-path validation warnings |
| `task.template.json` | `task` | Yes | `gates` + `soft_scoring` are consumed by scorer config loader |
| `task_config.template.json` | `task_config` | Yes | General runtime metadata; `runtime.llm.model` is used by `gen-cv` fallback model resolution |
| `user_profile.template.json` | `user_profile` | No | Used by prompt generation (`## Candidate Profile`) and profile metadata |
| `domain_schema.template.json` | `domain_schema` | No | Stored as profile metadata (not directly used in scorer pipeline) |
| `schema.template.json` | `result_schema` | No | Stored as profile metadata; can be used for schema documentation/custom tooling |

## 3) Template details

### 4.1 `constraints.template.json`

Purpose: define hard/soft search constraints.

Main sections:

- `domain`
- `sources` (`primary`, `secondary`, `fallback`)
- `must` (hard rules)
- `prefer` (soft boosts)
- `avoid` (soft penalties)
- `limits`
- `relaxation`

Rule format uses `ConstraintRule` semantics:

- `field`: dotted path (example: `geo.region`)
- `op`: one of `=`, `in`, `contains_any`, `contains_all`, `>=`, `<=`, `<`, `>`, `weighted`
- `value`: operator payload
- optional: `weight`, `weights`, `severity`, `neutral_if_na`, `reason`

### 4.2 `task.template.json`

Purpose: define task-level scoring behavior and related task metadata.

Runtime-critical sections:

- `gates`
- `soft_scoring`

Current scorer loader (`task_json_to_scoring_config`) reads:

- `gates.hard_filters_mode` (`any|all|require_any|require_all`)
- `gates.hard_filters`
- `gates.reject_anomalies`
- `gates.required_evidence_fields`
- `soft_scoring.formula_version`
- `soft_scoring.prefer_weight_default`
- `soft_scoring.avoid_penalty_default`
- `soft_scoring.signal_boost`
- `soft_scoring.penalties`

Other sections in this template (for example `deterministic_scoring`, `normalization`, `dedupe`) are allowed as task metadata and may be consumed by custom tooling.

### 4.3 `task_config.template.json`

Purpose: task runtime parameters and operational metadata.

Typical content:

- language/output preferences
- result targets
- runtime tuning
- capabilities flags
- artifact naming conventions

Important note:

- For `gen-cv` API flow, `task_config.runtime.llm.model` is part of the model name resolution chain.

### 4.4 `user_profile.template.json`

Purpose: optional candidate/user context attached to the profile.

Examples:

- focus roles
- seniority and stack preferences
- process preferences
- commute policy
- availability

Usage:

- included in prompt-generation output in API/application flow as `## Candidate Profile` when present.

### 4.5 `domain_schema.template.json`

Purpose: optional domain-level schema metadata and validation policy description.

Usage:

- persisted in bundle as `domain_schema`
- useful as explicit domain contract for teams and custom validators

### 4.6 `schema.template.json`

Purpose: optional JSON Schema for result record shape.

Usage:

- persisted in bundle as `result_schema`
- useful for external validation/documentation pipelines

## 5) Bootstrap a new profile from templates

Example (job search profile):

```bash
mkdir -p config/job_search/profile_new
cp config/templates/constraints.template.json config/job_search/profile_new/constraints.json
cp config/templates/task.template.json config/job_search/profile_new/task.json
cp config/templates/task_config.template.json config/job_search/profile_new/task_config.json
cp config/templates/user_profile.template.json config/job_search/profile_new/user_profile.json
cp config/templates/domain_schema.template.json config/job_search/profile_new/domain_schema.json
cp config/templates/schema.template.json config/job_search/profile_new/result_schema.json
```

Then compose `bundle.json`:

```json
{
  "profile_id": "profile_new",
  "constraints": {},
  "task": {},
  "task_config": {},
  "user_profile": {},
  "domain_schema": {},
  "result_schema": {}
}
```

Populate each object with the corresponding template payload.

## 6) Minimal valid bundle

This is the minimum shape accepted by bundle persistence validation:

```json
{
  "profile_id": "profile_1",
  "constraints": {
    "domain": "job_search",
    "must": [],
    "prefer": [],
    "avoid": []
  },
  "task": {
    "gates": {
      "hard_filters_mode": "any",
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

## 7) Validation behavior and common mistakes

`PUT /v1/job-search/profiles/{profile_id}/bundle` returns:

- `ok: true` when valid (may still include warnings)
- `ok: false` when invalid

Common issues:

- missing one of `constraints`, `task`, `task_config`
- invalid rule operator payloads (`weighted` without `weights`, non-list values for list operators, etc.)
- unknown field paths in rules (reported as warnings, not hard errors)
- using placeholders like `<task_name>` without replacing them
