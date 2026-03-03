import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi } from "vitest"

import { CvTab } from "@/components/tabs/cv-tab"
import type { WorkspaceStore } from "@/lib/store"
import { createWorkspaceMock } from "./helpers/workspace-mock"

let workspace: WorkspaceStore

const { hoisted } = vi.hoisted(() => ({
  hoisted: {
    workspaceRef: { current: null as WorkspaceStore | null },
    apiMock: {
      generateCv: vi.fn(),
    },
  },
}))

vi.mock("@/lib/store", () => ({
  useWorkspace: () => {
    if (!hoisted.workspaceRef.current) {
      throw new Error("Workspace mock not initialized")
    }
    return hoisted.workspaceRef.current
  },
}))

vi.mock("@/lib/api-client", () => ({
  api: hoisted.apiMock,
  API_RUNTIME: { base: "/api/mock/v1", isMock: true },
}))

describe("CvTab critical flow", () => {
  beforeEach(() => {
    workspace = createWorkspaceMock({
      activeProfileId: "profile_1",
      bundle: {
        profile_id: "profile_1",
        user_profile: { name: "Jane Doe", seniority: "senior", skills: ["Python", "FastAPI"] },
        constraints: { domain: "job_search", must: [], prefer: [], avoid: [] },
        task: { gates: {}, soft_scoring: {} },
        task_config: {},
      },
      run: {
        run_id: "run-1",
        profile_id: "profile_1",
        scored_records: [
          {
            id: "job-1",
            company: "Acme",
            title: "Senior Backend Engineer",
            modality: "remote",
            seniority: { level: "senior" },
            score: 8.5,
            gate_passed: true,
            gate_failures: [],
            anomalies: [],
          },
        ],
        metrics: {
          loaded: 1,
          processed: 1,
          skipped: 0,
          started_at: "2026-02-22T05:05:00.123456",
          finished_at: "2026-02-22T05:05:00.223456",
        },
        errors: [],
        snapshot_dir: "runs/run-1",
      },
      cv: null,
      cvStatus: "draft",
    })
    hoisted.workspaceRef.current = workspace
    hoisted.apiMock.generateCv.mockReset()
  })

  it("generates CV and renders markdown preview", async () => {
    hoisted.apiMock.generateCv.mockResolvedValue({
      cv_markdown: "# Generated CV\n\n## Summary\n\nSenior candidate aligned to role.\n\n- Python\n- FastAPI",
      generated_cv_json: {
        title: "Generated CV",
        summary: "Senior candidate aligned to role.",
      },
      model_info: {
        model: "lfm2.5-thinking",
      },
    })

    const { rerender } = render(<CvTab />)

    await userEvent.click(screen.getByRole("button", { name: /Acme/i }))
    await userEvent.click(screen.getByRole("button", { name: /Generar CV/i }))

    await waitFor(() => {
      expect(hoisted.apiMock.generateCv).toHaveBeenCalledTimes(1)
      expect(hoisted.apiMock.generateCv).toHaveBeenCalledWith(
        expect.objectContaining({
          profile_id: "profile_1",
          llm_model: "lfm2.5-thinking",
          allow_mock_fallback: true,
        })
      )
      expect(workspace.setCvStatus).toHaveBeenCalledWith("done")
      expect(workspace.setCv).toHaveBeenCalledTimes(1)
    })

    rerender(<CvTab />)

    expect(screen.getByText("Generated CV")).toBeInTheDocument()
    expect(screen.getByText(/Senior candidate aligned to role/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Export .md/i })).toBeInTheDocument()
  })

  it("shows error and skips API call when candidate override JSON is invalid", async () => {
    render(<CvTab />)

    await userEvent.click(screen.getByRole("button", { name: /Acme/i }))
    const textarea = screen.getByPlaceholderText(/\{/i)
    fireEvent.change(textarea, { target: { value: "{invalid-json" } })
    await userEvent.click(screen.getByRole("button", { name: /Generar CV/i }))

    expect(hoisted.apiMock.generateCv).not.toHaveBeenCalled()
    expect(
      screen.getByText(/JSON invalido en Candidate Override/i)
    ).toBeInTheDocument()
  })

  it("sends custom llm model when provided in UI", async () => {
    hoisted.apiMock.generateCv.mockResolvedValue({
      cv_markdown: "# Generated CV",
      generated_cv_json: { title: "Generated CV" },
      model_info: { model: "qwen2.5:latest" },
    })

    render(<CvTab />)

    await userEvent.click(screen.getByRole("button", { name: /Acme/i }))
    await userEvent.type(screen.getByPlaceholderText(/lfm2.5-thinking/i), "qwen2.5:latest")
    await userEvent.click(screen.getByRole("button", { name: /Generar CV/i }))

    await waitFor(() => {
      expect(hoisted.apiMock.generateCv).toHaveBeenCalledWith(
        expect.objectContaining({
          llm_model: "qwen2.5:latest",
        })
      )
    })
  })
})
