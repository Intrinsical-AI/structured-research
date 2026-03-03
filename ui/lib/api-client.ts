import {
  type Bundle,
  type BundleSaveResponse,
  type CvRequest,
  type CvResponse,
  type JsonlResponse,
  type ProfileSummary,
  type PromptRequest,
  type PromptResponse,
  type RunRequest,
  type RunResponse,
  WORKSPACE_TASK_ID,
} from "@/lib/contracts"

const RAW_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/mock/v1"
const BASE = RAW_BASE.replace(/\/+$/, "")

export const API_RUNTIME = {
  base: BASE,
  isMock: BASE.startsWith("/api/mock"),
} as const

function taskPath(taskId: string, suffix: string): string {
  const clean = suffix.startsWith("/") ? suffix : `/${suffix}`
  return `/tasks/${taskId}${clean}`
}

async function request(url: string, options?: RequestInit): Promise<unknown> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.message || `Request failed: ${res.status}`)
  }
  return res.json()
}

function parseResponse<T>(payload: unknown, endpoint: string): T {
  if (payload === null || payload === undefined) {
    throw new Error(`Invalid API response for ${endpoint}: <root> (empty payload)`)
  }
  return payload as T
}

export const api = {
  getProfiles: async (): Promise<ProfileSummary[]> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, "/profiles")
    const payload = await request(endpoint)
    if (!Array.isArray(payload)) {
      throw new Error(`Invalid API response for ${endpoint}: <root> (expected array)`)
    }
    return payload as ProfileSummary[]
  },

  getBundle: async (profileId: string): Promise<Bundle> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, `/profiles/${profileId}/bundle`)
    const payload = await request(endpoint)
    return parseResponse<Bundle>(payload, endpoint)
  },

  saveBundle: async (
    profileId: string,
    bundle: Bundle
  ): Promise<BundleSaveResponse> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, `/profiles/${profileId}/bundle`)
    const payload = await request(endpoint, {
      method: "PUT",
      body: JSON.stringify(bundle),
    })
    return parseResponse<BundleSaveResponse>(payload, endpoint)
  },

  generatePrompt: async (
    profileId: string,
    step: string = "S3_execute"
  ): Promise<PromptResponse> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, "/prompt/generate")
    const body: PromptRequest = { profile_id: profileId, step }
    const payload = await request(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    })
    return parseResponse<PromptResponse>(payload, endpoint)
  },

  validateJsonl: async (
    profileId: string,
    raw_jsonl: string
  ): Promise<JsonlResponse> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, "/jsonl/validate")
    const payload = await request(endpoint, {
      method: "POST",
      body: JSON.stringify({ profile_id: profileId, raw_jsonl }),
    })
    return parseResponse<JsonlResponse>(payload, endpoint)
  },

  executeRun: async (
    profileId: string,
    records: Record<string, unknown>[]
  ): Promise<RunResponse> => {
    const endpoint = taskPath(WORKSPACE_TASK_ID, "/run")
    const body: RunRequest = { profile_id: profileId, records }
    const payload = await request(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    })
    return parseResponse<RunResponse>(payload, endpoint)
  },

  generateCv: async (data: CvRequest): Promise<CvResponse> => {
    const endpoint = taskPath("gen_cv", "/actions/gen-cv")
    const payload = await request(endpoint, {
      method: "POST",
      body: JSON.stringify(data),
    })
    return parseResponse<CvResponse>(payload, endpoint)
  },
}
