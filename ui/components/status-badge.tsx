"use client"

import type { ProcessStatus } from "@/lib/contracts"
import { cn } from "@/lib/utils"

const statusConfig: Record<ProcessStatus, { label: string; className: string; dot: string }> = {
  draft: {
    label: "Draft",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/40",
  },
  valid: {
    label: "Valid",
    className: "bg-success/10 text-success",
    dot: "bg-success",
  },
  invalid: {
    label: "Invalid",
    className: "bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  running: {
    label: "Running",
    className: "bg-info/10 text-info",
    dot: "bg-info animate-pulse",
  },
  done: {
    label: "Done",
    className: "bg-accent text-accent-foreground",
    dot: "bg-accent-foreground/70",
  },
  failed: {
    label: "Failed",
    className: "bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
}

export function StatusBadge({ status }: { status: ProcessStatus }) {
  const config = statusConfig[status]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide",
        config.className
      )}
    >
      <span className={cn("h-1 w-1 shrink-0 rounded-full", config.dot)} />
      {config.label}
    </span>
  )
}
