"use client"

import { useRef, useState } from "react"
import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import type { JsonlResponse } from "@/lib/contracts"
import { StatusBadge } from "@/components/status-badge"
import { Upload, FileText, CheckCircle2, XCircle, AlertCircle, Layers } from "lucide-react"

const SAMPLE_JSONL = `{"id":"demo-001","source":"demo","company":"Vercel","title":"Senior Frontend Engineer","posted_at":"2026-02-20","apply_url":"https://example.com/jobs/1","geo":{"region":"EU","city":"Remote","country":"Spain"},"modality":"remote","seniority":{"level":"senior"},"stack":["React","Next.js"],"evidence":[{"id":"e1","field":"title","quote":"Senior Frontend Engineer","url":"https://example.com/jobs/1","retrieved_at":"2026-02-20T12:00:00Z","locator":{"type":"text_fragment","value":"Senior Frontend Engineer"},"source_kind":"html"}],"facts":[{"field":"title","value":"Senior Frontend Engineer","evidence_ids":["e1"]}],"inferences":[],"anomalies":[],"incomplete":false}
{"id":"demo-002","source":"demo","company":"Stripe","title":"Frontend Engineer","posted_at":"2026-02-19","apply_url":"https://example.com/jobs/2","geo":{"region":"US","city":"San Francisco","country":"USA"},"modality":"hybrid","seniority":{"level":"mid"},"stack":["React","TypeScript"],"evidence":[{"id":"e2","field":"title","quote":"Frontend Engineer","url":"https://example.com/jobs/2","retrieved_at":"2026-02-20T12:00:00Z","locator":{"type":"text_fragment","value":"Frontend Engineer"},"source_kind":"html"}],"facts":[{"field":"title","value":"Frontend Engineer","evidence_ids":["e2"]}],"inferences":[],"anomalies":[],"incomplete":false}
this is broken json line -- intentional error for demo
{"bad_record":true}
{"id":"demo-003","source":"demo","company":"Linear","title":"Staff Engineer","posted_at":"2026-02-18","apply_url":"https://example.com/jobs/3","geo":{"region":"EU","city":"Paris","country":"France"},"modality":"on_site","seniority":{"level":"staff"},"stack":["TypeScript"],"evidence":[{"id":"e3","field":"title","quote":"Staff Engineer","url":"https://example.com/jobs/3","retrieved_at":"2026-02-20T12:00:00Z","locator":{"type":"text_fragment","value":"Staff Engineer"},"source_kind":"html"}],"facts":[{"field":"title","value":"Staff Engineer","evidence_ids":["e3"]}],"inferences":[],"anomalies":[],"incomplete":false}`

export function JsonlTab() {
  const { activeProfileId, jsonl, jsonlStatus, jsonlRaw, setJsonl, setJsonlStatus, setJsonlRaw } = useWorkspace()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showInvalid, setShowInvalid] = useState(false)

  const handleValidate = async (raw?: string) => {
    const text = raw ?? jsonlRaw
    if (!activeProfileId || !text.trim()) return

    setJsonlStatus("running")
    try {
      const res = await api.validateJsonl(activeProfileId, text)
      setJsonl(res as JsonlResponse)
      const response = res as JsonlResponse
      setJsonlStatus(response.invalid_records.length === 0 ? "valid" : "done")
    } catch {
      setJsonlStatus("failed")
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      setJsonlRaw(text)
      handleValidate(text)
    }
    reader.readAsText(file)
  }

  const handleLoadSample = () => {
    setJsonlRaw(SAMPLE_JSONL)
    handleValidate(SAMPLE_JSONL)
  }

  const lineCount = jsonlRaw ? jsonlRaw.split("\n").filter((l) => l.trim()).length : 0

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">JSONL Validator</h2>
          <StatusBadge status={jsonlStatus} />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleLoadSample}
            className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground transition-all duration-200 hover:bg-surface-inset hover:text-foreground"
          >
            <FileText className="h-3.5 w-3.5" />
            Cargar demo
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground transition-all duration-200 hover:bg-surface-inset hover:text-foreground"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload .jsonl
          </button>
          <input ref={fileInputRef} type="file" accept=".jsonl,.json,.txt" onChange={handleFileUpload} className="hidden" />
          <button
            onClick={() => handleValidate()}
            disabled={jsonlStatus === "running" || !jsonlRaw.trim()}
            className="btn-shimmer flex items-center gap-1.5 rounded-md bg-gradient-accent px-4 py-1.5 text-xs font-medium text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent disabled:opacity-50"
          >
            Validar
          </button>
        </div>
      </div>

      {/* Textarea */}
      <div className="relative">
        <textarea
          value={jsonlRaw}
          onChange={(e) => setJsonlRaw(e.target.value)}
          placeholder={"Pega tu JSONL aqui, una linea por registro...\n\nO usa el boton 'Cargar demo' para probar con datos de ejemplo."}
          spellCheck={false}
          className="min-h-[200px] w-full resize-y rounded-lg border border-border-subtle bg-surface-inset p-4 font-mono text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/40 transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
        />
        {jsonlRaw && (
          <div className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-md border border-border-subtle bg-background/90 px-2 py-1 text-[10px] text-muted-foreground/60 backdrop-blur-sm">
            <Layers className="h-2.5 w-2.5" />
            {lineCount} lineas
          </div>
        )}
      </div>

      {/* Metrics */}
      {jsonl && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="Total lineas" value={jsonl.metrics.total_lines} />
            <MetricCard label="JSON valido" value={jsonl.metrics.json_valid_lines} />
            <MetricCard label="Schema valido" value={jsonl.metrics.schema_valid_records} variant="success" />
            <MetricCard label="Invalidos" value={jsonl.metrics.invalid_lines} variant={jsonl.metrics.invalid_lines > 0 ? "error" : "neutral"} />
          </div>

          {/* Valid records summary */}
          {jsonl.valid_records.length > 0 && (
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-foreground/70" />
                <span className="text-xs font-medium text-foreground">{jsonl.valid_records.length} registros validos</span>
              </div>
              <div className="max-h-[240px] overflow-auto space-y-1">
                {jsonl.valid_records.map((rec, i) => {
                  const r = rec as Record<string, unknown>
                  return (
                    <div key={i} className="flex items-center gap-2 rounded-md bg-surface-inset px-3 py-1.5 text-xs">
                      <span className="w-6 shrink-0 text-right font-mono text-muted-foreground/50">{i + 1}</span>
                      <span className="font-medium text-foreground">{r.company as string}</span>
                      <span className="text-border">|</span>
                      <span className="text-muted-foreground">{r.title as string}</span>
                      <span className="ml-auto rounded border border-border-subtle bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground/70">
                        {r.modality as string}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Invalid records */}
          {jsonl.invalid_records.length > 0 && (
            <div className="rounded-lg border border-destructive/20 bg-surface p-4">
              <button
                onClick={() => setShowInvalid(!showInvalid)}
                className="flex w-full items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <XCircle className="h-3.5 w-3.5 text-destructive" />
                  <span className="text-xs font-medium text-destructive">
                    {jsonl.invalid_records.length} registros invalidos
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground">{showInvalid ? "Ocultar" : "Mostrar detalles"}</span>
              </button>
              {showInvalid && (
                <div className="mt-3 max-h-[200px] space-y-2 overflow-auto">
                  {jsonl.invalid_records.map((rec, i) => (
                    <div key={i} className="rounded-md bg-destructive/[0.04] px-3 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />
                        <span className="font-mono text-muted-foreground">Linea {rec.line}</span>
                        <span className="text-destructive">{rec.error}</span>
                      </div>
                      <pre className="mt-1 truncate text-[10px] text-muted-foreground/60">{rec.raw}</pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!jsonl && jsonlStatus === "draft" && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface py-20">
          <Upload className="mb-3 h-6 w-6 text-muted-foreground/30" />
          <p className="text-xs font-medium text-muted-foreground">Pega JSONL o sube un archivo para validar</p>
          <button
            onClick={handleLoadSample}
            className="mt-3 text-[11px] text-muted-foreground/60 underline underline-offset-2 transition-colors duration-200 hover:text-foreground"
          >
            o carga datos de ejemplo
          </button>
        </div>
      )}
    </div>
  )
}

function MetricCard({
  label,
  value,
  variant = "neutral",
}: {
  label: string
  value: number
  variant?: "neutral" | "success" | "error"
}) {
  return (
    <div className={`rounded-lg border p-4 bg-surface ${
      variant === "error" && value > 0 ? "border-destructive/25" : "border-border"
    }`}>
      <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">{label}</p>
      <p
        className={`mt-1.5 text-2xl font-bold tabular-nums ${
          variant === "error" && value > 0 ? "text-destructive" : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  )
}
