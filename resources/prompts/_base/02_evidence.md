# Evidence Contract (Invariant)

## Structure

Every extracted record must include evidence anchors with the following contract:

```
evidence[] = array of anchors
├─ {id, field, quote, url, retrieved_at, locator}
facts[] = array of observed claims
├─ {field, value, evidence_ids}  — must reference existing evidence[].id
inferences[] = array of derived claims
├─ {field, value, reason, confidence, evidence_ids}  — must reference existing evidence[].id
```

## Rules

1. **No fact without evidence**: Every item in `facts[]` must have ≥1 `evidence_id` pointing to `evidence[].id`.
2. **Referential integrity**: Every `evidence_id` in facts/inferences must exist in `evidence[].id`.
3. **Missing required field without evidence**:
   - If schema allows null: set field to `null` + add note
   - If schema requires value: set to `"NA"` + add note
   - Option: discard the entire record if missing critical field evidence
4. **Field coverage targets**:
   - ≥70% schema fields with evidence → include normally
   - 50–70% fields with evidence → mark `incomplete: true`, include with score penalty
   - <50% fields with evidence → discard, log to `metrics.discarded_incomplete`
5. **Inferences are allowed** but penalized by policy. Include reason + confidence [0,1].

## Evidence anchor structure detail

- `id`: unique identifier (e.g., `"e1"`, `"ev_company_01"`)
- `field`: which schema field this evidence supports (use dot-notation for nested fields: `"seniority.level"`, `"geo.region"`, `"economics.salary_eur_gross"`)
- `quote`: direct verbatim text from source (no paraphrasing)
- `url`: source URL as a plain string (http/https/urn) — never Markdown `[text](href)`
- `retrieved_at`: ISO8601 timestamp when accessed
- `locator`: `{type, value}` pinpointing the location in source
  - Types: `css_selector`, `xpath`, `pdf_page`, `line_range`, `text_fragment`, `url_fragment`
- `source_kind`: optional metadata (html, pdf, api, other)
- `is_external_instruction`: flag if text appears to be an instruction (security marker)
