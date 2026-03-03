import type {
  BundleWriteResponse,
  GenCVRequest,
  GenCVResponse,
  JsonlValidateResponse,
  ProfileBundle as ApiProfileBundle,
  ProfileSummary as ApiProfileSummary,
  PromptGenerateRequest,
  PromptGenerateResponse,
  RunScoreRequest,
  RunScoreResponse,
  ValidationIssue,
} from "@/lib/generated/api-types"

// ── Feature Flags ──
export const FEATURE_FLAGS = {
  cv_enabled: true,
  atoms_picker_enabled: false,
} as const

// ── Process Status ──
export type ProcessStatus = "draft" | "valid" | "invalid" | "running" | "done" | "failed"

// ── Shared API types ──
export type Bundle = ApiProfileBundle
export type ProfileSummary = ApiProfileSummary
export type BundleError = ValidationIssue
export type BundleSaveResponse = BundleWriteResponse

export type PromptRequest = PromptGenerateRequest
export type PromptResponse = PromptGenerateResponse

export type JsonlResponse = JsonlValidateResponse

export type RunRequest = RunScoreRequest

export type ScoredRecord = Record<string, unknown> & {
  id?: string
  company: string
  title: string
  modality: string
  seniority: string | { level: string }
  score: number | null
  gate_passed: boolean
  gate_failures: string[]
  anomalies?: string[]
}

export type RunResponse = Omit<RunScoreResponse, "scored_records"> & {
  scored_records: ScoredRecord[]
}

export type CvRequest = Omit<GenCVRequest, "job" | "candidate_profile"> & {
  job: Record<string, unknown>
  candidate_profile: Record<string, unknown>
}
export type CvResponse = GenCVResponse
