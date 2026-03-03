# S0 — Intent

## Objective

Identify and confirm the task objective before any search or prospecting begins.

## Actions

1. **Load all inputs** from `config/job_search/schemas/`:
   - `task_config.json` (budget, mode, runtime settings)
   - `constraints.json` (must/prefer/avoid, sources, relaxation)
   - `user_profile.json` (user preferences, seniority, tech stack, location policy)
   - `task.json` (gates, soft_scoring rules, normalization maps)
   - `domain_schema.json` (field definitions, allowed values)

2. **State the objective** in one sentence:
   - Example: "Find mid/senior Python backend engineer roles with remote or ≤2 days hybrid in EU, salary ≥€35k/year, with evidence for each key field."

3. **Confirm expected result type**:
   - Entity: `job_posting`
   - Scoring: [0,10] scale (0 = failed gates, 10 = all prefer signals + boosts)
   - Output format: `scored_results.jsonl`

4. **Identify key constraints** (from loaded config):
   - Must have: modality, seniority level, region/timezone
   - Preferred: salary range, tech stack, domain tags
   - Avoid: on-site only, old postings, etc.
   - Sources: primary (LinkedIn, Wellfound, Greenhouse, Lever), secondary (Indeed, Glassdoor), fallback (careers pages, RemoteOK)

5. **Check for blockers**:
   - Missing required input files → BLOCKER
   - Contradictory constraints (e.g., must be remote AND must be Madrid office) → BLOCKER / ASK
   - Impossible target (target_results[0] > max_results with realistic sources) → ASK
   - Capability mismatch (need PDF parse but unavailable) → BLOCKER

## Output Format

```
S0 INTENT:
═══════════════════════════════════════════════════════════════
Objective: Find [entity type] matching user preferences with evidence
Target: N–M valid job_posting records
Key must-haves: [comma-separated from constraints.must]
Preferred signals: [comma-separated from constraints.prefer]
Blockers: [list or NONE]
═══════════════════════════════════════════════════════════════

Next step: [S1 CLARIFY if blockers or ambiguity / S3 EXECUTE if config is solid]
```

## Decision

- **If blockers**: Stop and report. Return blocker manifest.
- **If no blockers**: Proceed to S1 (clarify if ≥1 required field is ambiguous) or S3 (execute if config is solid).
