# Job Search — Domain Context

## Domain

`job_search` — find and extract job postings that match the provided constraints.

## Result Entity

A `job_posting` is a single job listing. Every record must include:

| Field | Type | Notes |
|-------|------|-------|
| `company` | string | Company name as listed |
| `title` | string | Job title as listed |
| `posted_at` | ISO8601 date or null | When the posting was published (null if unknown) |
| `apply_url` | URL | Full link to apply |
| `geo` | object | `region` required; `city`, `country` optional |
| `modality` | enum | `remote` \| `hybrid` \| `on_site` |
| `seniority` | object | `level`: `junior` \| `mid` \| `senior` \| `staff` |
| `evidence` | array | ≥1 anchor per record |

## Normalization

**Modality** — map free text to enum:
- "work from home", "fully remote", "100% remote", "teletrabajo" → `remote`
- "hybrid", "2–3 days office", "flexible", "híbrido", "semipresencial" → `hybrid`
- "on-site", "in-office", "office only", "presencial" → `on_site`

**Seniority** — map to enum:
- "junior", "trainee", "intern", "graduate", "entry-level" → `junior`
- "mid", "associate", "<5 years", "intermediate" → `mid`
- "senior", "lead", "tech lead" → `senior`
- "staff engineer", "principal", "distinguished" → `staff`

**Salary** — always report as annual gross. If only monthly given, multiply by 12. Note currency assumptions.

**posted_at** — normalize to ISO8601. Relative dates ("3 days ago") → compute from today.

## Sources

Consult the search constraints for the ordered list of sources to use. If no sources are listed, prioritise major job boards for the relevant country/sector, followed by company career pages.

## Deduplication

Primary key: `company + apply_url`. Fallback: `company + title + location`.
