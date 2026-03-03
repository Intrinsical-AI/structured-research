import { NextResponse } from "next/server"

function toScoredRecord(input: Record<string, unknown>, index: number) {
  const baseScore = 10 - index * 0.8
  const score = Math.max(0, Math.min(10, Number(baseScore.toFixed(2))))
  const gate_passed = score >= 5.5
  return {
    ...input,
    id: input.id ?? `rec-${index + 1}`,
    gate_passed,
    gate_failures: gate_passed ? [] : ["mock_gate_failure"],
    score,
    anomalies: gate_passed ? [] : ["mock_low_fit"],
  }
}

export async function POST(req: Request) {
  const { profile_id, records } = await req.json()
  const input = Array.isArray(records) ? (records as Record<string, unknown>[]) : []
  const started_at = new Date().toISOString()

  await new Promise((r) => setTimeout(r, 400))

  const scored_records = input.map(toScoredRecord)
  const gate_passed = scored_records.filter((r) => r.gate_passed).length
  const gate_failed = scored_records.length - gate_passed
  return NextResponse.json({
    run_id: `${profile_id || "profile"}-${Date.now()}`,
    profile_id,
    scored_records,
    metrics: {
      loaded: input.length,
      processed: scored_records.length,
      skipped: 0,
      gate_passed,
      gate_failed,
      gate_pass_rate: scored_records.length > 0 ? gate_passed / scored_records.length : 0,
      started_at,
      finished_at: new Date().toISOString(),
    },
    errors: [],
    snapshot_dir: null,
    snapshot_status: "failed",
    snapshot_error: "mock backend does not persist snapshots",
  })
}
