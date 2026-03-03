"use client"

import { useEffect, useState } from "react"
import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import type { Bundle, BundleError } from "@/lib/contracts"
import { StatusBadge } from "@/components/status-badge"
import { Save, Code2, FormInput, AlertCircle, Check, Loader2 } from "lucide-react"

const SECTIONS = ["user_profile", "constraints", "task", "task_config"] as const
type Section = (typeof SECTIONS)[number]

const sectionMeta: Record<Section, { label: string; description: string }> = {
  user_profile: { label: "User Profile", description: "Datos del candidato: skills, experiencia, preferencias" },
  constraints: { label: "Constraints", description: "Gates obligatorios, nice-to-have y dealbreakers" },
  task: { label: "Task", description: "Objetivo de busqueda y pasos del pipeline" },
  task_config: { label: "Task Config", description: "Modelo de scoring, pesos y umbrales" },
}

export function ConfigTab() {
  const { bundle, bundleStatus, bundleErrors, activeProfileId, setBundle, setBundleStatus, setBundleErrors } = useWorkspace()
  const [mode, setMode] = useState<"form" | "json">("json")
  const [activeSection, setActiveSection] = useState<Section>("user_profile")
  const [editBuffer, setEditBuffer] = useState<string>("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (!bundle) return
    const data = bundle[activeSection as keyof Bundle]
    setEditBuffer(JSON.stringify(data ?? {}, null, 2))
    setJsonError(null)
    setSaveSuccess(false)
  }, [bundle, activeSection])

  const handleSectionChange = (section: Section) => {
    setActiveSection(section)
  }

  const handleSave = async () => {
    if (!activeProfileId || !bundle) return

    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(editBuffer)
    } catch {
      setJsonError("Invalid JSON syntax")
      setBundleStatus("invalid")
      return
    }
    setJsonError(null)

    const updated = { ...bundle, [activeSection]: parsed }
    setBundleStatus("running")
    setBundleErrors([])
    setSaveSuccess(false)

    try {
      const res = await api.saveBundle(activeProfileId, updated as Bundle)
      if (res.ok) {
        setBundle(updated as Bundle)
        setBundleErrors((res.errors || []) as BundleError[])
        setBundleStatus("valid")
        setSaveSuccess(true)
        setTimeout(() => setSaveSuccess(false), 2000)
      } else {
        setBundleErrors((res.errors || []) as BundleError[])
        setBundleStatus("invalid")
      }
    } catch {
      setBundleStatus("failed")
    }
  }

  const sectionErrors = bundleErrors.filter((e) => e.path.startsWith(activeSection))
  const hasBlockingErrors = sectionErrors.some((e) => e.severity !== "warning")

  if (!bundle) {
    return (
      <div className="flex items-center justify-center py-28">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Cargando configuracion...
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">Configuracion</h2>
          <StatusBadge status={bundleStatus} />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMode(mode === "json" ? "form" : "json")}
            className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground transition-all duration-200 hover:bg-surface-inset hover:text-foreground"
          >
            {mode === "json" ? <FormInput className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
            {mode === "json" ? "Form View" : "JSON View"}
          </button>
          <button
            onClick={handleSave}
            disabled={bundleStatus === "running"}
            className="btn-shimmer flex items-center gap-1.5 rounded-md bg-gradient-accent px-3 py-1.5 text-xs font-medium text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent disabled:opacity-50"
          >
            {bundleStatus === "running" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : saveSuccess ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            {saveSuccess ? "Guardado" : "Guardar"}
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        {/* Section nav */}
        <nav className="flex flex-row gap-1 lg:flex-col">
          {SECTIONS.map((s) => {
            const hasErrors = bundleErrors.some((e) => e.path.startsWith(s))
            const meta = sectionMeta[s]
            const isActive = activeSection === s
            return (
              <button
                key={s}
                onClick={() => handleSectionChange(s)}
                className={`group flex flex-col items-start rounded-lg px-3 py-2.5 text-left transition-all duration-200 ${
                  isActive
                    ? "bg-foreground text-background shadow-sm"
                    : "bg-surface text-muted-foreground hover:bg-surface-inset hover:text-foreground"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-medium">{meta.label}</span>
                  {hasErrors && (
                    <AlertCircle className={`h-3 w-3 ${isActive ? "text-background/60" : "text-destructive"}`} />
                  )}
                </div>
                <span className={`mt-0.5 text-[10px] leading-snug hidden lg:block ${
                  isActive ? "text-background/60" : "text-muted-foreground/60"
                }`}>
                  {meta.description}
                </span>
              </button>
            )
          })}
        </nav>

        {/* Editor */}
        <div className="space-y-4">
          {/* Errors */}
          {sectionErrors.length > 0 && (
            <div className={`rounded-lg p-4 space-y-2 ${
              hasBlockingErrors
                ? "border border-destructive/20 bg-destructive/[0.04]"
                : "border border-amber-200 bg-amber-50/60"
            }`}>
              {sectionErrors.map((err, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <AlertCircle
                    className={`mt-0.5 h-3 w-3 shrink-0 ${
                      err.severity === "warning" ? "text-amber-600" : "text-destructive"
                    }`}
                  />
                  <div>
                    <span
                      className={`font-mono ${
                        err.severity === "warning" ? "text-amber-700" : "text-destructive"
                      }`}
                    >
                      {err.path}
                    </span>
                    <span className="text-muted-foreground"> — {err.message}</span>
                    <span className="ml-1 text-muted-foreground/60">({err.code})</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {jsonError && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/[0.04] px-4 py-3 text-xs text-destructive">
              <AlertCircle className="h-3 w-3 shrink-0" />
              {jsonError}
            </div>
          )}

          {mode === "json" ? (
            <div className="relative">
              <textarea
                value={editBuffer}
                onChange={(e) => {
                  setEditBuffer(e.target.value)
                  setJsonError(null)
                  setSaveSuccess(false)
                }}
                spellCheck={false}
                className="min-h-[420px] w-full resize-y rounded-lg border border-border-subtle bg-surface-inset p-4 font-mono text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/40 transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
              />
              <div className="absolute bottom-3 right-3 text-[10px] text-muted-foreground/40 font-mono">
                {activeSection}
              </div>
            </div>
          ) : (
            <FormView
              data={(bundle[activeSection as keyof Bundle] as Record<string, unknown>) ?? {}}
              onChange={(updated) => {
                setEditBuffer(JSON.stringify(updated, null, 2))
                setBundle({ ...bundle, [activeSection]: updated } as Bundle)
                setSaveSuccess(false)
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function FormView({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (data: Record<string, unknown>) => void
}) {
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed border-border bg-surface py-16">
        <p className="text-xs text-muted-foreground">No hay campos configurados</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {entries.map(([key, value]) => (
        <div key={key} className="group rounded-lg border border-border-subtle bg-surface p-4 transition-all duration-200 hover:border-border">
          <label className="mb-2 block text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">
            {key.replace(/_/g, " ")}
          </label>
          {typeof value === "string" || typeof value === "number" ? (
            <input
              type={typeof value === "number" ? "number" : "text"}
              value={String(value)}
              onChange={(e) => {
                const v = typeof value === "number" ? Number(e.target.value) : e.target.value
                onChange({ ...data, [key]: v })
              }}
              className="w-full rounded-md border border-border-subtle bg-background px-3 py-2 text-xs text-foreground transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
            />
          ) : typeof value === "boolean" ? (
            <button
              onClick={() => onChange({ ...data, [key]: !value })}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                value ? "bg-foreground text-background" : "bg-surface-inset text-muted-foreground hover:text-foreground"
              }`}
            >
              {String(value)}
            </button>
          ) : Array.isArray(value) ? (
            <div className="flex flex-wrap gap-1.5">
              {value.map((item, idx) => (
                <span
                  key={idx}
                  className="rounded-md bg-surface-inset px-2 py-1 text-xs text-foreground"
                >
                  {typeof item === "object" ? JSON.stringify(item) : String(item)}
                </span>
              ))}
            </div>
          ) : value !== null && typeof value === "object" ? (
            <pre className="rounded-md bg-surface-inset p-3 text-[10px] font-mono text-muted-foreground leading-relaxed overflow-x-auto">
              {JSON.stringify(value, null, 2)}
            </pre>
          ) : (
            <span className="text-xs text-muted-foreground/50">null</span>
          )}
        </div>
      ))}
    </div>
  )
}
