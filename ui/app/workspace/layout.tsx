import type { Metadata } from "next"
import { WorkspaceProvider } from "@/components/workspace-provider"

export const metadata: Metadata = {
  title: "Workspace | Job Search",
  description: "Configure, generate, validate and score job search results.",
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <WorkspaceProvider>{children}</WorkspaceProvider>
}
