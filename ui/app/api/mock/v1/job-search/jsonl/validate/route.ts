import { NextResponse } from "next/server"

type Invalid = { line: number; error: string; raw: string; kind: string }

function looksLikeJobPosting(obj: Record<string, unknown>): boolean {
  return Boolean(
    obj.id &&
      obj.source &&
      obj.company &&
      obj.title &&
      obj.posted_at &&
      obj.apply_url &&
      obj.geo &&
      obj.modality &&
      obj.seniority
  )
}

export async function POST(req: Request) {
  const { raw_jsonl } = await req.json()
  const lines = String(raw_jsonl ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)

  const valid_records: Record<string, unknown>[] = []
  const invalid_records: Invalid[] = []

  lines.forEach((line, idx) => {
    try {
      const parsed = JSON.parse(line) as Record<string, unknown>
      if (!looksLikeJobPosting(parsed)) {
        invalid_records.push({
          line: idx + 1,
          error: "Schema validation failed: missing required job posting fields",
          raw: line.slice(0, 200),
          kind: "schema_validation",
        })
      } else {
        valid_records.push(parsed)
      }
    } catch (e) {
      invalid_records.push({
        line: idx + 1,
        error: e instanceof Error ? e.message : "Invalid JSON syntax",
        raw: line.slice(0, 200),
        kind: "json_parse",
      })
    }
  })

  await new Promise((r) => setTimeout(r, 250))
  return NextResponse.json({
    valid_records,
    invalid_records,
    metrics: {
      total_lines: lines.length,
      json_valid_lines: lines.length - invalid_records.filter((r) => r.kind === "json_parse").length,
      schema_valid_records: valid_records.length,
      invalid_lines: invalid_records.length,
    },
  })
}

