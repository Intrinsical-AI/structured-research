import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi } from "vitest"

import { ConfigTab } from "@/components/tabs/config-tab"
import type { WorkspaceStore } from "@/lib/store"
import { createWorkspaceMock } from "./helpers/workspace-mock"

let workspace: WorkspaceStore

const { hoisted } = vi.hoisted(() => ({
  hoisted: {
    workspaceRef: { current: null as WorkspaceStore | null },
    apiMock: {
      saveBundle: vi.fn(),
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

const baseBundle = {
  profile_id: "profile_1",
  user_profile: { role_focus: ["Senior Python Engineer"] },
  constraints: { domain: "job_search", must: [], prefer: [], avoid: [] },
  task: { gates: {}, soft_scoring: {} },
  task_config: { agent_name: "test" },
}

describe("ConfigTab critical flows", () => {
  beforeEach(() => {
    workspace = createWorkspaceMock({
      activeProfileId: "profile_1",
      bundle: baseBundle,
      bundleStatus: "draft",
      bundleErrors: [],
    })
    hoisted.workspaceRef.current = workspace
    hoisted.apiMock.saveBundle.mockReset()
  })

  it("marks save as valid when backend returns ok=true (with warnings)", async () => {
    hoisted.apiMock.saveBundle.mockResolvedValue({
      ok: true,
      errors: [
        {
          path: "constraints.must[1].field",
          code: "unknown_field_path",
          message: "unknown field",
          severity: "warning",
        },
      ],
    })

    render(<ConfigTab />)
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }))

    await waitFor(() => {
      expect(hoisted.apiMock.saveBundle).toHaveBeenCalledTimes(1)
      expect(workspace.setBundleStatus).toHaveBeenCalledWith("valid")
      expect(workspace.setBundleErrors).toHaveBeenCalledWith([
        {
          path: "constraints.must[1].field",
          code: "unknown_field_path",
          message: "unknown field",
          severity: "warning",
        },
      ])
    })
  })

  it("marks save as invalid when backend returns ok=false", async () => {
    hoisted.apiMock.saveBundle.mockResolvedValue({
      ok: false,
      errors: [
        {
          path: "constraints.must.0.value",
          code: "list_type",
          message: "Input should be a valid list",
          severity: "error",
        },
      ],
    })

    render(<ConfigTab />)
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }))

    await waitFor(() => {
      expect(hoisted.apiMock.saveBundle).toHaveBeenCalledTimes(1)
      expect(workspace.setBundleStatus).toHaveBeenCalledWith("invalid")
      expect(workspace.setBundleErrors).toHaveBeenCalledWith([
        {
          path: "constraints.must.0.value",
          code: "list_type",
          message: "Input should be a valid list",
          severity: "error",
        },
      ])
    })
  })
})
