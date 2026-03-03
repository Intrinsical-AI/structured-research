"use client"

import { useState } from "react"
import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import type { ScoredRecord } from "@/lib/contracts"
import { toast } from "@/hooks/use-toast"
import { StatusBadge } from "@/components/status-badge"
import { FileDown, Sparkles, Eye, Code2, User, Loader2, ChevronRight } from "lucide-react"

const DEFAULT_LLM_MODEL = "lfm2.5-thinking"

function scoreOf(record: ScoredRecord): number {
  return typeof record.score === "number" ? record.score : 0
}

function taskConfigModel(taskConfig: unknown): string | null {
  if (!taskConfig || typeof taskConfig !== "object") return null
  const runtime = (taskConfig as Record<string, unknown>).runtime
  if (!runtime || typeof runtime !== "object") return null
  const llm = (runtime as Record<string, unknown>).llm
  if (!llm || typeof llm !== "object") return null
  const model = (llm as Record<string, unknown>).model
  if (typeof model !== "string") return null
  const trimmed = model.trim()
  return trimmed.length > 0 ? trimmed : null
}

export function CvTab() {
  const { activeProfileId, bundle, run, cv, cvStatus, setCv, setCvStatus } = useWorkspace()
  const [selectedJob, setSelectedJob] = useState<ScoredRecord | null>(null)
  const [viewMode, setViewMode] = useState<"preview" | "json">("preview")
  const [candidateJson, setCandidateJson] = useState<string>("")
  const [candidateJsonError, setCandidateJsonError] = useState<string | null>(null)
  const [llmModel, setLlmModel] = useState<string>("")

  const handleGenerate = async () => {
    if (!activeProfileId || !selectedJob) return

    const defaultCandidate = {
      id: "demo-candidate",
      seniority: "senior",
      tech_stack: {
        languages: ["typescript", "python"],
      }
    }
    let candidate = defaultCandidate
    if (candidateJson.trim()) {
      try {
        candidate = JSON.parse(candidateJson)
        setCandidateJsonError(null)
      } catch {
        setCandidateJsonError("JSON invalido en Candidate Override.")
        setCvStatus("invalid")
        return
      }
    } else {
      setCandidateJsonError(null)
    }

    const fallbackModel = taskConfigModel(bundle?.task_config) ?? DEFAULT_LLM_MODEL
    const effectiveLlmModel = llmModel.trim() || fallbackModel

    setCvStatus("running")
    const progressToast = toast({
      title: "Generando CV...",
      description: `Consultando ${effectiveLlmModel}. Esto puede tardar unos segundos.`,
    })
    try {
      const res = await api.generateCv({
        profile_id: activeProfileId,
        job: selectedJob as unknown as Record<string, unknown>,
        candidate_profile: candidate as Record<string, unknown>,
        llm_model: effectiveLlmModel,
        allow_mock_fallback: true,
      })
      setCv(res)
      setCvStatus("done")
      progressToast.dismiss()
      toast({
        title: "CV generado",
        description: "Respuesta recibida y renderizada.",
      })
    } catch (error) {
      setCvStatus("failed")
      const message =
        error instanceof Error && error.message
          ? error.message
          : "No se pudo generar el CV."
      progressToast.dismiss()
      toast({
        title: "Error generando CV",
        description: message,
        variant: "destructive",
      })
    }
  }

  const handleExport = () => {
    if (!cv?.cv_markdown) return
    const blob = new Blob([cv.cv_markdown], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `cv-${selectedJob?.company?.toLowerCase().replace(/\s+/g, "-") || "generated"}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scoredRecords = run?.scored_records?.filter((r: ScoredRecord) => r.gate_passed) ?? []

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">CV Generator</h2>
          <StatusBadge status={cvStatus} />
        </div>
        {cv && (
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground transition-all duration-200 hover:bg-surface-inset hover:text-foreground"
          >
            <FileDown className="h-3.5 w-3.5" />
            Export .md
          </button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Left: Selection + candidate */}
        <div className="space-y-4">
          {/* Job selection */}
          <div className="rounded-lg border border-border bg-surface p-4">
            <h3 className="mb-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">
              Seleccionar oferta (Gate OK)
            </h3>
            {scoredRecords.length === 0 ? (
              <div className="py-6 text-center">
                <p className="text-xs text-muted-foreground">
                  Ejecuta el scoring primero
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground/60">
                  Solo ofertas que pasen los gates estaran disponibles
                </p>
              </div>
            ) : (
              <div className="max-h-[260px] space-y-1 overflow-auto">
                {scoredRecords.map((r: ScoredRecord, i: number) => (
                  <button
                    key={i}
                    onClick={() => setSelectedJob(r)}
                    className={`flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-xs transition-all duration-200 ${selectedJob === r
                        ? "bg-foreground text-background shadow-sm"
                        : "bg-background text-foreground hover:bg-surface-inset"
                      }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate font-medium">{r.company}</span>
                        <span className={`font-mono text-[10px] tabular-nums ${selectedJob === r ? "text-background/60" : "text-muted-foreground/50"
                          }`}>
                          {scoreOf(r).toFixed(2)}
                        </span>
                      </div>
                      <span className={`block truncate text-[10px] ${selectedJob === r ? "text-background/60" : "text-muted-foreground"
                        }`}>
                        {r.title}
                      </span>
                    </div>
                    <ChevronRight className={`h-3 w-3 shrink-0 ${selectedJob === r ? "text-background/40" : "text-muted-foreground/30"
                      }`} />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Candidate profile */}
          <div className="rounded-lg border border-border bg-surface p-4">
            <div className="mb-2 flex items-center gap-2">
              <User className="h-3 w-3 text-muted-foreground/60" />
              <h3 className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">
                Candidate Override
              </h3>
            </div>
            <div className="mb-3">
              <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">
                LLM Model
              </label>
              <input
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                placeholder={taskConfigModel(bundle?.task_config) ?? DEFAULT_LLM_MODEL}
                className="w-full rounded-md border border-border-subtle bg-surface-inset px-3 py-2 font-mono text-[11px] text-foreground placeholder:text-muted-foreground/40 transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
              />
            </div>
            <p className="mb-3 text-[11px] text-muted-foreground/60 leading-relaxed">
              JSON opcional. Si esta vacio, se usa el user_profile del bundle actual.
            </p>
            <textarea
              value={candidateJson}
              onChange={(e) => {
                setCandidateJson(e.target.value)
                setCandidateJsonError(null)
              }}
              placeholder={`{\n  "id": "demo-candidate",\n  "seniority": "senior"\n}`}
              spellCheck={false}
              className="min-h-[100px] w-full resize-y rounded-md border border-border-subtle bg-surface-inset p-3 font-mono text-[10px] leading-relaxed text-foreground placeholder:text-muted-foreground/20 transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
            />
            {candidateJsonError && (
              <p className="mt-2 text-[11px] text-destructive">{candidateJsonError}</p>
            )}
          </div>

          <button
            onClick={handleGenerate}
            disabled={!selectedJob || cvStatus === "running"}
            className="btn-shimmer flex w-full items-center justify-center gap-1.5 rounded-md bg-gradient-accent px-4 py-2.5 text-xs font-medium text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent disabled:opacity-50"
          >
            {cvStatus === "running" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {cvStatus === "running" ? "Generando..." : "Generar CV"}
          </button>
        </div>

        {/* Right: Preview */}
        <div>
          {cvStatus === "running" ? (
            <div className="flex min-h-[380px] flex-col items-center justify-center rounded-lg border border-border bg-surface p-8">
              <Loader2 className="mb-3 h-6 w-6 animate-spin text-foreground/50" />
              <p className="text-sm font-medium text-foreground">Generando CV...</p>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Esperando respuesta del LLM local y aplicando grounding.
              </p>
            </div>
          ) : cv ? (
            <div className="space-y-4">
              {/* View toggle + meta */}
              <div className="flex items-center gap-2">
                <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
                  <button
                    onClick={() => setViewMode("preview")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-all duration-200 ${viewMode === "preview"
                        ? "bg-foreground text-background shadow-sm"
                        : "text-muted-foreground hover:bg-surface-inset hover:text-foreground"
                      }`}
                  >
                    <Eye className="h-3.5 w-3.5" />
                    Preview
                  </button>
                  <button
                    onClick={() => setViewMode("json")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-all duration-200 ${viewMode === "json"
                        ? "bg-foreground text-background shadow-sm"
                        : "text-muted-foreground hover:bg-surface-inset hover:text-foreground"
                      }`}
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    JSON
                  </button>
                </div>

                {cv.model_info && (
                  <div className="ml-auto flex items-center gap-2 text-[10px] font-mono text-muted-foreground/50">
                    {(() => {
                      const info = cv.model_info as Record<string, unknown>
                      const parts = [typeof info.model === "string" ? info.model : "unknown"]
                      if (typeof info.tokens_used === "number") parts.push(`${info.tokens_used} tok`)
                      if (typeof info.latency_ms === "number") parts.push(`${info.latency_ms}ms`)
                      return parts.map((part, idx) => (
                        <span key={part + idx}>
                          {idx > 0 && <span className="mr-2 text-muted-foreground/20">|</span>}
                          {part}
                        </span>
                      ))
                    })()}
                    {(() => {
                      const info = cv.model_info as Record<string, unknown>
                      return info.fallback_used === true ? (
                        <span className="rounded border border-amber-400/40 bg-amber-50 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-amber-600">
                          mock fallback
                        </span>
                      ) : null
                    })()}
                  </div>
                )}
              </div>

              {viewMode === "preview" ? (
                <div className="rounded-lg border border-border bg-background p-10 md:p-12">
                  <MarkdownPreview content={cv.cv_markdown} />
                </div>
              ) : (
                <pre className="max-h-[500px] overflow-auto rounded-lg border border-border bg-surface-inset p-6 text-xs leading-relaxed text-foreground/80">
                  {JSON.stringify(cv.generated_cv_json, null, 2)}
                </pre>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface py-28">
              <Sparkles className="mb-3 h-6 w-6 text-muted-foreground/30" />
              <p className="text-xs font-medium text-muted-foreground">Selecciona una oferta y genera el CV</p>
              <p className="mt-1.5 text-[11px] text-muted-foreground/60">
                El CV se adapta automaticamente al puesto y empresa seleccionados
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function MarkdownPreview({ content }: { content: string }) {
  const lines = content.split("\n")

  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("### ")) {
          return (
            <h3 key={i} className="mt-7 mb-2 text-[11px] font-semibold uppercase tracking-widest text-foreground">
              {line.replace("### ", "")}
            </h3>
          )
        }
        if (line.startsWith("## ")) {
          return (
            <h2 key={i} className="mt-4 border-b border-border-subtle pb-1 text-sm text-muted-foreground">
              {line.replace("## ", "")}
            </h2>
          )
        }
        if (line.startsWith("# ")) {
          return (
            <h1 key={i} className="text-2xl font-bold tracking-tight text-foreground">
              {line.replace("# ", "")}
            </h1>
          )
        }
        if (line.startsWith("- ")) {
          return (
            <li key={i} className="ml-4 list-disc text-[13px] leading-relaxed text-muted-foreground">
              {renderInlineMarkdown(line.replace("- ", ""))}
            </li>
          )
        }
        if (line.startsWith("**") && line.includes("**") && line.includes("|")) {
          const clean = line.replace(/\*\*/g, "")
          const parts = clean.split("|").map((p) => p.trim())
          return (
            <div key={i} className="mt-3 flex flex-wrap items-baseline gap-1.5 text-[13px]">
              <span className="font-semibold text-foreground">{parts[0]}</span>
              {parts.slice(1).map((part, pi) => (
                <span key={pi} className="text-muted-foreground/60">
                  {part}
                  {pi < parts.length - 2 && <span className="mx-1 text-muted-foreground/20">/</span>}
                </span>
              ))}
            </div>
          )
        }
        if (line.startsWith("**")) {
          return (
            <p key={i} className="text-[13px] leading-relaxed">
              {renderInlineMarkdown(line)}
            </p>
          )
        }
        if (line.startsWith("|")) {
          const cells = line.split("|").filter(Boolean).map((c) => c.trim())
          if (cells.every((c) => c.match(/^-+$/))) return null
          return (
            <div key={i} className="flex gap-4 text-[10px] font-mono text-muted-foreground/60">
              {cells.map((cell, ci) => (
                <span key={ci} className="min-w-[100px]">{cell}</span>
              ))}
            </div>
          )
        }
        if (line.trim() === "") return <div key={i} className="h-1.5" />
        return (
          <p key={i} className="text-[13px] leading-relaxed text-muted-foreground">
            {renderInlineMarkdown(line)}
          </p>
        )
      })}
    </div>
  )
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/)
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-foreground">
          {part.replace(/\*\*/g, "")}
        </strong>
      )
    }
    return <span key={i}>{part}</span>
  })
}
