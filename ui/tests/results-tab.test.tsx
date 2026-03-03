import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi } from "vitest"

import { ResultsTab } from "@/components/tabs/results-tab"
import type { WorkspaceStore } from "@/lib/store"
import { createWorkspaceMock } from "./helpers/workspace-mock"

let workspace: WorkspaceStore

const { hoisted } = vi.hoisted(() => ({
  hoisted: {
    workspaceRef: { current: null as WorkspaceStore | null },
    apiMock: {
      executeRun: vi.fn(),
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

describe("ResultsTab critical flow", () => {
  beforeEach(() => {
    workspace = createWorkspaceMock({
      activeProfileId: "profile_1",
      jsonl: {
        valid_records: [
          { id: "job-1", company: "Acme", title: "Senior Engineer", modality: "remote" },
          { id: "job-2", company: "Globex", title: "Junior Engineer", modality: "on_site" },
        ],
        invalid_records: [],
        metrics: { total_lines: 2, json_valid_lines: 2, schema_valid_records: 2, invalid_lines: 0 },
      },
      run: null,
      runStatus: "draft",
    })
    hoisted.workspaceRef.current = workspace
    hoisted.apiMock.executeRun.mockReset()
  })

  it("executes run and renders score/gate results", async () => {
    hoisted.apiMock.executeRun.mockResolvedValue({
      run_id: "profile_1-20260222-050500-a1b2c3",
      profile_id: "profile_1",
      scored_records: [
        {
          id: "job-1",
          company: "Acme",
          title: "Senior Engineer",
          modality: "remote",
          seniority: { level: "senior" },
          score: 8.2,
          gate_passed: true,
          gate_failures: [],
          anomalies: [],
        },
        {
          id: "job-2",
          company: "Globex",
          title: "Junior Engineer",
          modality: "on_site",
          seniority: { level: "junior" },
          score: 3.5,
          gate_passed: false,
          gate_failures: ["modality_not_allowed"],
          anomalies: ["low_confidence"],
        },
      ],
      metrics: {
        loaded: 2,
        processed: 2,
        skipped: 0,
        started_at: "2026-02-22T05:05:00.123456",
        finished_at: "2026-02-22T05:05:00.223456",
      },
      errors: [],
      snapshot_dir: "runs/profile_1-20260222-050500-a1b2c3",
    })

    const { rerender } = render(<ResultsTab />)
    await userEvent.click(screen.getByRole("button", { name: /Ejecutar Scoring/i }))

    await waitFor(() => {
      expect(hoisted.apiMock.executeRun).toHaveBeenCalledWith("profile_1", workspace.jsonl?.valid_records ?? [])
      expect(workspace.setRunStatus).toHaveBeenCalledWith("done")
      expect(workspace.setRun).toHaveBeenCalledTimes(1)
    })

    rerender(<ResultsTab />)

    expect(screen.getByText("Acme")).toBeInTheDocument()
    expect(screen.getByText("Globex")).toBeInTheDocument()
    expect(screen.getAllByText("8.20").length).toBeGreaterThan(0)
    expect(screen.getAllByText("3.50").length).toBeGreaterThan(0)
    expect(screen.getByText(/modality not allowed/i)).toBeInTheDocument()
  })
})
