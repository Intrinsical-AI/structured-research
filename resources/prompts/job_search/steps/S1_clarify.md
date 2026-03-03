# S1 — Clarify Configuration (Optional)

## When to Run

Only if **≥1 required field has ambiguous or missing value** in the loaded task configuration.

Skip S1 if config is already executable quality (≥60% required fields are unambiguous).

## Protocol

Ask only what is **strictly needed** to reach executable config quality.

**Max 3 questions** per iteration. Group by topic. Focus on:
- Ambiguous constraint values (e.g., salary currency not specified)
- Missing user preferences that affect gate/scoring (e.g., location ambiguity)
- Source availability / region feasibility

## Question Template

```
S1 CLARIFY — Iteration [N/3]:

Based on the task config, I have [N] questions before proceeding to execution:

1. [Question about ambiguous constraint]
   - Current state: [what we know]
   - Why needed: [impact on gates or scoring]
   - Options: [A | B | C]

2. [Next question...]

Please answer, or I will proceed with: [explicit default assumptions]
```

## Exit Criteria

- **≥60% required-field coverage** is now unambiguous, OR
- **Max 3 iterations reached**: Proceed with explicit assumptions documented

If proceeding with assumptions:
```
S1 ASSUMPTIONS (iteration limit reached):
- Assumption 1: [field] = [value] because [reasoning]
- Assumption 2: ...

Proceeding to S3 with these assumptions.
```

## Clarification Examples

- "User profile doesn't specify remote-only or hybrid preference. Assuming hybrid is acceptable per modality values."
- "Salary currency unclear. Using user_profile.currency_default = EUR."
- "Region list in constraints includes 'US-remote-CET-overlap' but user is in Madrid. Assuming timezone overlap acceptable."
