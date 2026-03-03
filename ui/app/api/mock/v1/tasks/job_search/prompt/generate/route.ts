import { NextResponse } from "next/server"

export async function POST(req: Request) {
  const { profile_id, step } = await req.json()
  const selectedStep = typeof step === "string" ? step : "S3_execute"
  const selectedProfile = typeof profile_id === "string" ? profile_id : "profile_example"

  const prompt = [
    `# Mock Prompt (${selectedStep})`,
    "",
    `Profile: ${selectedProfile}`,
    "",
    "Return ONLY JSONL records, one JSON object per line.",
    "",
    "## Search Constraints",
    "```json",
    JSON.stringify({ must: [{ field: "modality", op: "in", value: ["remote", "hybrid"] }] }, null, 2),
    "```",
  ].join("\n")

  await new Promise((r) => setTimeout(r, 300))
  return NextResponse.json({
    profile_id: selectedProfile,
    step: selectedStep,
    prompt,
    constraints_embedded: true,
    prompt_hash: `sha256:${Math.random().toString(16).slice(2).padEnd(64, "0").slice(0, 64)}`,
  })
}
