import { NextResponse } from "next/server"

export async function POST(req: Request) {
  const { job, candidate_profile } = await req.json()

  const title = (job?.title as string) || "Role"
  const company = (job?.company as string) || "Company"
  const candidateName = (candidate_profile?.name as string) || "Candidate"

  await new Promise((r) => setTimeout(r, 500))

  const generated_cv_json = {
    job_id: job?.id || "job",
    candidate_id: candidate_profile?.id || "candidate",
    title: `${title} @ ${company}`,
    summary: `${candidateName} aligned with ${title}.`,
    highlights: [
      "Generated from mock endpoint.",
      "Switch NEXT_PUBLIC_API_BASE to point to FastAPI for real output.",
    ],
    grounded_claim_ids: [],
  }

  const cv_markdown = [
    `# ${generated_cv_json.title}`,
    "",
    "## Summary",
    "",
    generated_cv_json.summary,
    "",
    "## Highlights",
    "",
    ...generated_cv_json.highlights.map((h) => `- ${h}`),
    "",
  ].join("\n")

  return NextResponse.json({
    generated_cv_json,
    cv_markdown,
    model_info: {
      model: "mock",
      profile_id: "mock",
    },
  })
}
