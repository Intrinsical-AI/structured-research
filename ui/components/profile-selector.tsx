"use client"

import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import type { Bundle } from "@/lib/contracts"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { User } from "lucide-react"

export function ProfileSelector() {
  const {
    profiles,
    activeProfileId,
    setActiveProfile,
    setBundle,
    setBundleStatus,
    setBundleErrors,
    setPrompt,
    setPromptStatus,
    setJsonl,
    setJsonlStatus,
    setJsonlRaw,
    setRun,
    setRunStatus,
    setCv,
    setCvStatus,
  } = useWorkspace()

  async function handleSelect(profileId: string) {
    setActiveProfile(profileId)
    setPrompt(null)
    setPromptStatus("draft")
    setJsonl(null)
    setJsonlStatus("draft")
    setJsonlRaw("")
    setRun(null)
    setRunStatus("draft")
    setCv(null)
    setCvStatus("draft")
    setBundleStatus("running")
    setBundleErrors([])
    try {
      const bundle = await api.getBundle(profileId)
      setBundle(bundle as Bundle)
      setBundleStatus("valid")
    } catch {
      setBundleStatus("failed")
    }
  }

  return (
    <Select value={activeProfileId || undefined} onValueChange={handleSelect}>
      <SelectTrigger className="h-8 w-[240px] border-border bg-background/50 text-xs backdrop-blur-sm gap-2">
        <User className="h-3 w-3 text-muted-foreground/50 shrink-0" />
        <SelectValue placeholder="Seleccionar perfil..." />
      </SelectTrigger>
      <SelectContent>
        {profiles.map((p) => (
          <SelectItem key={p.id} value={p.id} className="text-xs">
            <div className="flex flex-col">
              <span>{p.name}</span>
              <span className="text-[10px] text-muted-foreground/50">
                {new Date(p.updated_at).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" })}
              </span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
