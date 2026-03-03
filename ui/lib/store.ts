"use client"

import type {
  Bundle,
  BundleError,
  ProcessStatus,
  PromptResponse,
  JsonlResponse,
  RunResponse,
  CvResponse,
  ProfileSummary,
} from "./contracts"

export interface WorkspaceState {
  // Profile
  profiles: ProfileSummary[]
  activeProfileId: string | null

  // Bundle / Config
  bundle: Bundle | null
  bundleStatus: ProcessStatus
  bundleErrors: BundleError[]

  // Prompt
  prompt: PromptResponse | null
  promptStatus: ProcessStatus

  // JSONL
  jsonl: JsonlResponse | null
  jsonlStatus: ProcessStatus
  jsonlRaw: string

  // Run
  run: RunResponse | null
  runStatus: ProcessStatus

  // CV
  cv: CvResponse | null
  cvStatus: ProcessStatus
}

export interface WorkspaceActions {
  setProfiles: (profiles: ProfileSummary[]) => void
  setActiveProfile: (id: string) => void
  setBundle: (bundle: Bundle) => void
  setBundleStatus: (status: ProcessStatus) => void
  setBundleErrors: (errors: BundleError[]) => void
  setPrompt: (prompt: PromptResponse | null) => void
  setPromptStatus: (status: ProcessStatus) => void
  setJsonl: (jsonl: JsonlResponse | null) => void
  setJsonlStatus: (status: ProcessStatus) => void
  setJsonlRaw: (raw: string) => void
  setRun: (run: RunResponse | null) => void
  setRunStatus: (status: ProcessStatus) => void
  setCv: (cv: CvResponse | null) => void
  setCvStatus: (status: ProcessStatus) => void
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions

export const initialState: WorkspaceState = {
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
}

import { create } from "zustand"

export const useWorkspace = create<WorkspaceStore>((set) => ({
  ...initialState,
  setProfiles: (profiles) => set({ profiles }),
  setActiveProfile: (activeProfileId) => set({ activeProfileId }),
  setBundle: (bundle) => set({ bundle }),
  setBundleStatus: (bundleStatus) => set({ bundleStatus }),
  setBundleErrors: (bundleErrors) => set({ bundleErrors }),
  setPrompt: (prompt) => set({ prompt }),
  setPromptStatus: (promptStatus) => set({ promptStatus }),
  setJsonl: (jsonl) => set({ jsonl }),
  setJsonlStatus: (jsonlStatus) => set({ jsonlStatus }),
  setJsonlRaw: (jsonlRaw) => set({ jsonlRaw }),
  setRun: (run) => set({ run }),
  setRunStatus: (runStatus) => set({ runStatus }),
  setCv: (cv) => set({ cv }),
  setCvStatus: (cvStatus) => set({ cvStatus }),
}))
