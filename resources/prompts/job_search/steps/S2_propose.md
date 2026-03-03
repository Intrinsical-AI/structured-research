# S2 — Propose Config + Negotiate (Optional)

## When to Run

Only if you identify a **clearly better config** or a **mandatory adjustment** after reviewing S1 clarification.

Skip S2 if configuration is good as-is and requirements are met.

## Proposal Format

```
S2 PROPOSAL — Cycle [N/3]:

CHANGE: [field path in constraints or task]
FROM:   [current value]
TO:     [proposed value]
REASON: [Why this is better/necessary]
  - [specific benefit 1]
  - [specific benefit 2]
TRADEOFF: [What is gained | What is lost]
ALTERNATIVES:
  - Option A: [description]
  - Option B: [description]
```

## Negotiation

- Present 1–2 proposals per cycle
- **Max 3 cycles**: If no agreement after 3, auto-select the **balanced option** and explain reasoning
- User can always override

## Feasibility Check (Before S3)

**Do not proceed to S3 without validating**:

1. **Capabilities**: All `task_config.capabilities_required` are available
   - web_browse: can fetch web pages
   - http_fetch: can request URLs
   - html_parse: can parse HTML
   - pdf_parse: can read PDFs
   - json_io: can parse JSON
   → If blocking capability missing: STOP, request alternative config

2. **Sources**: Primary sources in `constraints.sources.primary` are reachable
   - LinkedIn, Wellfound, Greenhouse, Lever: assume available
   - Company career pages: check URLs are accessible
   → If primary sources unavailable: warn, suggest relying on secondary/fallback

3. **Budget**: Estimated pages + time can meet `target_results[0]`
   - Rough estimate: average 5 pages per result, 30 sec per page = 2.5 min per result
   - Target 18 results = ~45 pages = ~22 min (default budget = 30 min) ✓
   → If budget too tight: warn or ask for larger budget

## Auto-Select Logic (if max cycles reached)

```
S2 AUTO-SELECT (after 3 cycles):
Selecting balanced option: [which option]
REASONING:
- [trade-off reason 1]
- [trade-off reason 2]

Proceeding to S3 with updated config.
```
