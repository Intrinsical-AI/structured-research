import { vi } from "vitest"

import type { WorkspaceStore } from "@/lib/store"
import type {
  Bundle,
  BundleError,
  CvResponse,
  JsonlResponse,
  ProcessStatus,
  ProfileSummary,
  PromptResponse,
  RunResponse,
} from "@/lib/contracts"

const baseState = {
  profiles: [],
  activeProfileId: null,
  bundle: null,
  bundleStatus: "draft",
  bundleErrors: [],
  prompt: null,
  promptStatus: "draft",
  jsonl: null,
  jsonlStatus: "draft",
  jsonlRaw: "",
  run: null,
  runStatus: "draft",
  cv: null,
  cvStatus: "draft",
} as const

export function createWorkspaceMock(overrides: Partial<WorkspaceStore> = {}): WorkspaceStore {
  const workspace = {
    ...baseState,
    ...overrides,
  } as WorkspaceStore

  workspace.setProfiles = vi.fn((profiles: ProfileSummary[]) => {
    workspace.profiles = profiles
  })
  workspace.setActiveProfile = vi.fn((id: string) => {
    workspace.activeProfileId = id
  })
  workspace.setBundle = vi.fn((bundle: Bundle) => {
    workspace.bundle = bundle
  })
  workspace.setBundleStatus = vi.fn((status: ProcessStatus) => {
    workspace.bundleStatus = status
  })
  workspace.setBundleErrors = vi.fn((errors: BundleError[]) => {
    workspace.bundleErrors = errors
  })
  workspace.setPrompt = vi.fn((prompt: PromptResponse | null) => {
    workspace.prompt = prompt
  })
  workspace.setPromptStatus = vi.fn((status: ProcessStatus) => {
    workspace.promptStatus = status
  })
  workspace.setJsonl = vi.fn((jsonl: JsonlResponse | null) => {
    workspace.jsonl = jsonl
  })
  workspace.setJsonlStatus = vi.fn((status: ProcessStatus) => {
    workspace.jsonlStatus = status
  })
  workspace.setJsonlRaw = vi.fn((raw: string) => {
    workspace.jsonlRaw = raw
  })
  workspace.setRun = vi.fn((run: RunResponse | null) => {
    workspace.run = run
  })
  workspace.setRunStatus = vi.fn((status: ProcessStatus) => {
    workspace.runStatus = status
  })
  workspace.setCv = vi.fn((cv: CvResponse | null) => {
    workspace.cv = cv
  })
  workspace.setCvStatus = vi.fn((status: ProcessStatus) => {
    workspace.cvStatus = status
  })

  return workspace
}
