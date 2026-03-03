# Guardrails (Invariant)

## S1 Clarification Phase

- **Max 3 questions** per iteration
- **Max 3 iterations** total
- **Exit criteria**: ≥60% required-field coverage is unambiguous, OR max iterations reached
- If max iterations reached: proceed with explicit assumptions documented

## S2 Proposal / Negotiation Phase

- **Max 3 proposal cycles**
- If agreement not reached after 3 cycles: **auto-select balanced option** and explain reasoning clearly
- User can always override

## Feasibility Check (Before S3 Execution)

**Required in guided/assisted modes:**

- Validate all `task_config.capabilities_required` are available (web_browse, http_fetch, html_parse, pdf_parse, json_io, etc.)
- Verify `constraints.sources.primary` are reachable / available
- Check execution budget is sufficient for target results
- **Blockers**: Stop execution if critical capability is missing
- **Warnings**: Non-critical issues require explicit user acknowledgment

## Execution Budget

Limits enforce scope and prevent runaway execution:

- **`budget.pages_max`** (default 300): Stop fetching after this many pages
- **`budget.time_minutes_max`** (default 30): Stop after this many minutes of runtime
- **Max relaxation cycles**: 5 (constraints loosening steps)

**If budget exhausted before target results met**:
- Set `metrics.scarcity: true`
- Return partial results with clear explanation
- Document which relaxation steps were applied

## Collaborative Checkpoint

- At ~40% budget use: Report interim metrics and allow user adjustments
- Format: `[MM:SS elapsed] [N/target results] [M% complete] — proceed? yes/no/adjust`

## Relaxation Policy (S3 context)

Triggered **only when** `valid_results < target_results[0]`:

- Apply sequentially using `constraints.relaxation.order`
- **Prioritize source expansion** before quality degradation
- Apply one step at a time, re-evaluate after each
- Stop as soon as target lower bound is reached OR budget exhausted
- Log all applied relaxations in `metrics.applied_relaxations`
