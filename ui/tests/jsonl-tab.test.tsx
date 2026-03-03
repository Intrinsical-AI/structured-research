import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi } from "vitest"

import { JsonlTab } from "@/components/tabs/jsonl-tab"
import type { WorkspaceStore } from "@/lib/store"
import { createWorkspaceMock } from "./helpers/workspace-mock"

let workspace: WorkspaceStore

const { hoisted } = vi.hoisted(() => ({
  hoisted: {
    workspaceRef: { current: null as WorkspaceStore | null },
    apiMock: {
      validateJsonl: vi.fn(),
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

describe("JsonlTab critical flow", () => {
  beforeEach(() => {
    workspace = createWorkspaceMock({
      activeProfileId: "profile_example",
      jsonlStatus: "draft",
      jsonlRaw: "",
      jsonl: null,
    })
    hoisted.workspaceRef.current = workspace
    hoisted.apiMock.validateJsonl.mockReset()
  })

  it("handles multiline/broken JSONL and sets status done when invalid records exist", async () => {
    const raw = [
      '{"id":"ok-1","company":"Acme","title":"Engineer"}',
      '{"id":"multi-2",',
      '"company":"Globex"',
      'this is broken',
    ].join("\n")
    workspace.jsonlRaw = raw

    hoisted.apiMock.validateJsonl.mockResolvedValue({
      valid_records: [{ id: "ok-1", company: "Acme", title: "Engineer", modality: "remote" }],
      invalid_records: [
        { line: 4, error: "Expecting value", raw: "this is broken", kind: "json_parse" },
      ],
      metrics: {
        total_lines: 4,
        json_valid_lines: 2,
        schema_valid_records: 1,
        invalid_lines: 1,
      },
    })

    const { rerender } = render(<JsonlTab />)
    await userEvent.click(screen.getByRole("button", { name: "Validar" }))

    await waitFor(() => {
      expect(hoisted.apiMock.validateJsonl).toHaveBeenCalledWith("profile_example", raw)
      expect(workspace.setJsonlStatus).toHaveBeenCalledWith("done")
      expect(workspace.setJsonl).toHaveBeenCalledTimes(1)
    })

    rerender(<JsonlTab />)
    expect(screen.getByText(/registros invalidos/i)).toBeInTheDocument()
  })
})
