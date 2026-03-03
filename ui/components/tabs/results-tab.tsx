"use client"

import { useState, useMemo } from "react"
import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import type { RunResponse, ScoredRecord } from "@/lib/contracts"
import { StatusBadge } from "@/components/status-badge"
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table"
import { Play, Clock, Layers, Filter, TrendingUp, AlertTriangle } from "lucide-react"
import { StaggerList, StaggerItem, motion } from "@/components/ui/motion"

type GateFilter = "all" | "passed" | "failed"

function scoreOf(record: ScoredRecord): number {
  return typeof record.score === "number" ? record.score : 0
}

function scoreValue(record: ScoredRecord): number | null {
  return typeof record.score === "number" ? record.score : null
}

function scoreText(record: ScoredRecord): string {
  const score = scoreValue(record)
  return score === null ? "N/A" : score.toFixed(2)
}

function seniorityLabel(record: ScoredRecord): string {
  if (typeof record.seniority === "string") return record.seniority
  if (record.seniority && typeof record.seniority === "object" && "level" in record.seniority) {
    const level = (record.seniority as { level?: unknown }).level
    return typeof level === "string" ? level : "unknown"
  }
  return "unknown"
}

export function ResultsTab() {
  const { activeProfileId, jsonl, run, runStatus, setRun, setRunStatus } = useWorkspace()
  const [gateFilter, setGateFilter] = useState<GateFilter>("all")
  const [scoreMin, setScoreMin] = useState(0)
  const [scoreMax, setScoreMax] = useState(10)
  const [anomaliesOnly, setAnomaliesOnly] = useState(false)

  const handleRun = async () => {
    if (!activeProfileId) return
    const records = jsonl?.valid_records ?? []
    setRunStatus("running")
    try {
      const res = await api.executeRun(activeProfileId, records)
      setRun(res as RunResponse)
      setRunStatus("done")
    } catch {
      setRunStatus("failed")
    }
  }

  const filteredRecords = useMemo(() => {
    if (!run?.scored_records) return []
    return run.scored_records.filter((r: ScoredRecord) => {
      if (gateFilter === "passed" && !r.gate_passed) return false
      if (gateFilter === "failed" && r.gate_passed) return false
      const score = scoreValue(r)
      if (score !== null && (score < scoreMin || score > scoreMax)) return false
      if (anomaliesOnly && (!r.anomalies || r.anomalies.length === 0)) return false
      return true
    })
  }, [run, gateFilter, scoreMin, scoreMax, anomaliesOnly])

  const stats = useMemo(() => {
    if (!run?.scored_records || run.scored_records.length === 0) return null
    const records = run.scored_records
    const passed = records.filter((r: ScoredRecord) => r.gate_passed)
    const failed = records.filter((r: ScoredRecord) => !r.gate_passed)
    const numericScores = records
      .map((r: ScoredRecord) => scoreValue(r))
      .filter((s): s is number => s !== null)
    const avg =
      numericScores.length > 0
        ? numericScores.reduce((a: number, b: number) => a + b, 0) / numericScores.length
        : 0
    const withAnomalies = records.filter((r: ScoredRecord) => r.anomalies && r.anomalies.length > 0)
    return {
      total: records.length,
      passed: passed.length,
      failed: failed.length,
      avgScore: avg,
      maxScore: numericScores.length > 0 ? Math.max(...numericScores) : 0,
      minScore: numericScores.length > 0 ? Math.min(...numericScores) : 0,
      anomalyCount: withAnomalies.length,
    }
  }, [run])

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">Resultados</h2>
          <StatusBadge status={runStatus} />
        </div>
        <button
          onClick={handleRun}
          disabled={runStatus === "running" || !activeProfileId}
          className="btn-shimmer flex items-center gap-1.5 rounded-md bg-gradient-accent px-4 py-1.5 text-xs font-medium text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent disabled:opacity-50"
        >
          {runStatus === "running" ? (
            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          Ejecutar Scoring
        </button>
      </div>

      {run && stats && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <StaggerList className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
            <StaggerItem><SummaryCard label="Total" value={stats.total} /></StaggerItem>
            <StaggerItem><SummaryCard label="Gate OK" value={stats.passed} variant="highlight" /></StaggerItem>
            <StaggerItem><SummaryCard label="Gate Fail" value={stats.failed} variant="dimmed" /></StaggerItem>
            <StaggerItem><SummaryCard label="Avg Score" value={stats.avgScore.toFixed(2)} /></StaggerItem>
            <StaggerItem><SummaryCard label="Max" value={stats.maxScore.toFixed(2)} variant="highlight" /></StaggerItem>
            <StaggerItem><SummaryCard label="Min" value={stats.minScore.toFixed(2)} variant="dimmed" /></StaggerItem>
            <StaggerItem><SummaryCard label="Anomalias" value={stats.anomalyCount} variant={stats.anomalyCount > 0 ? "warn" : "neutral"} /></StaggerItem>
          </StaggerList>

          {/* ETL Metadata */}
          <div className="flex flex-wrap items-center gap-4 rounded-lg border glass-subtle px-4 py-3">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Layers className="h-3 w-3" />
              <span className="font-mono">{run.run_id}</span>
            </div>
            <div className="h-3 w-px bg-border-subtle" />
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <TrendingUp className="h-3 w-3" />
              {run.metrics.processed} procesados / {run.metrics.skipped} omitidos
              {" · gate "}
              {Math.round((run.metrics.gate_pass_rate ?? 0) * 100)}%
            </div>
            <div className="h-3 w-px bg-border-subtle" />
            <div className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground/60">
              <Clock className="h-2.5 w-2.5" />
              {new Date(run.metrics.started_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              {" → "}
              {new Date(run.metrics.finished_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Filter className="h-3 w-3" />
              Filtros
            </div>

            {/* Gate filter */}
            <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
              {(["all", "passed", "failed"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setGateFilter(f)}
                  className={`rounded-md px-2.5 py-1 text-[10px] font-medium transition-all duration-200 ${
                    gateFilter === f
                      ? "bg-foreground text-background shadow-sm"
                      : "text-muted-foreground hover:bg-surface-inset hover:text-foreground"
                  }`}
                >
                  {f === "all" ? "Todos" : f === "passed" ? "Gate OK" : "Gate Fail"}
                </button>
              ))}
            </div>

            {/* Score range */}
            <div className="flex items-center gap-2">
              <label className="text-[10px] text-muted-foreground">Score</label>
              <input
                type="number"
                min={0}
                max={10}
                step={0.5}
                value={scoreMin}
                onChange={(e) => setScoreMin(Number(e.target.value))}
                className="h-7 w-14 rounded-md border border-border-subtle bg-surface-inset px-2 text-center font-mono text-[10px] text-foreground transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
              />
              <span className="text-[10px] text-muted-foreground">–</span>
              <input
                type="number"
                min={0}
                max={10}
                step={0.5}
                value={scoreMax}
                onChange={(e) => setScoreMax(Number(e.target.value))}
                className="h-7 w-14 rounded-md border border-border-subtle bg-surface-inset px-2 text-center font-mono text-[10px] text-foreground transition-all duration-200 focus:border-border focus:outline-none focus:ring-2 focus:ring-foreground/15"
              />
            </div>

            {/* Anomalies toggle */}
            <button
              onClick={() => setAnomaliesOnly(!anomaliesOnly)}
              className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[10px] font-medium transition-all duration-200 ${
                anomaliesOnly
                  ? "border-foreground bg-foreground text-background shadow-sm"
                  : "border-border bg-surface text-muted-foreground hover:bg-surface-inset hover:text-foreground"
              }`}
            >
              <AlertTriangle className="h-2.5 w-2.5" />
              Anomalias
            </button>

            <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">
              {filteredRecords.length} / {run.scored_records.length}
            </span>
          </div>

          {/* Results Table */}
          <div className="overflow-hidden rounded-lg border border-border shadow-elevation-sm">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent bg-surface">
                  <TableHead className="w-8 text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">#</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Company</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Title</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Modality</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Seniority</TableHead>
                  <TableHead className="w-[140px] text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Score (0–10)</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Gate</TableHead>
                  <TableHead className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">Issues</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRecords.map((r: ScoredRecord & { id?: string }, i: number) => {
                  const score = scoreValue(r)
                  const width = score === null ? 0 : Math.max(0, Math.min(100, (score / 10) * 100))
                  return (
                    <motion.tr
                      key={r.id || i}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.8), ease: [0.22, 1, 0.36, 1] }}
                      className="border-border-subtle transition-colors duration-150 hover:bg-surface border-b"
                    >
                      <TableCell className="font-mono text-[10px] text-muted-foreground/40">{i + 1}</TableCell>
                      <TableCell className="text-xs font-medium text-foreground">{r.company}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">{r.title}</TableCell>
                      <TableCell>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                          r.modality === "remote"
                            ? "bg-foreground/[0.07] text-foreground"
                            : r.modality === "hybrid"
                            ? "bg-surface-inset text-muted-foreground"
                            : "bg-surface-inset text-muted-foreground/60"
                        }`}>
                          {r.modality === "on_site" ? "on-site" : r.modality}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="rounded bg-surface-inset border border-border-subtle px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {seniorityLabel(r)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-surface-inset overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                scoreOf(r) >= 8 ? "bg-gradient-accent" :
                                scoreOf(r) >= 6 ? "bg-foreground/55" :
                                "bg-foreground/25"
                              }`}
                              style={{ width: `${width}%` }}
                            />
                          </div>
                          <span className="w-8 text-right font-mono text-[10px] font-bold tabular-nums text-foreground">
                            {scoreText(r)}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold ${
                            r.gate_passed
                              ? "bg-gradient-accent text-white"
                              : "bg-surface-inset border border-border text-muted-foreground/60"
                          }`}
                        >
                          {r.gate_passed ? "✓" : "✗"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {r.gate_failures.map((f, fi) => (
                            <span key={fi} className="rounded bg-destructive/[0.06] border border-destructive/15 px-1.5 py-0.5 text-[9px] text-destructive">
                              {f.replace(/_/g, " ")}
                            </span>
                          ))}
                          {r.anomalies?.map((a, ai) => (
                            <span key={`a-${ai}`} className="flex items-center gap-0.5 rounded bg-surface-inset border border-border-subtle px-1.5 py-0.5 text-[9px] text-muted-foreground">
                              <AlertTriangle className="h-2 w-2" />
                              {a.replace(/_/g, " ")}
                            </span>
                          ))}
                          {r.gate_failures.length === 0 && (!r.anomalies || r.anomalies.length === 0) && (
                            <span className="text-[10px] text-muted-foreground/30">—</span>
                          )}
                        </div>
                      </TableCell>
                    </motion.tr>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {!run && runStatus === "draft" && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border glass-subtle py-24">
          <Play className="mb-3 h-6 w-6 text-muted-foreground/30" />
          <p className="text-xs font-medium text-muted-foreground">Ejecuta el scoring para ver resultados</p>
          <p className="mt-1.5 text-[11px] text-muted-foreground/60">
            {jsonl?.valid_records?.length
              ? `${jsonl.valid_records.length} registros listos desde JSONL`
              : "Valida datos JSONL primero (paso anterior)"}
          </p>
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  label,
  value,
  variant = "neutral",
}: {
  label: string
  value: string | number
  variant?: "neutral" | "highlight" | "dimmed" | "warn"
}) {
  return (
    <div className={`rounded-lg border p-3 bg-surface shadow-elevation-xs transition-shadow duration-200 hover:shadow-elevation-sm ${
      variant === "warn" ? "border-destructive/20" :
      variant === "highlight" ? "border-foreground/10 bg-gradient-accent-subtle" :
      "border-border"
    }`}>
      <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/70">{label}</p>
      <p className={`mt-1 text-lg font-bold tabular-nums ${
        variant === "warn" ? "text-destructive" :
        variant === "dimmed" ? "text-muted-foreground" :
        "text-foreground"
      }`}>
        {value}
      </p>
    </div>
  )
}
