"use client"

import { useState } from "react"
import { useWorkspace } from "@/lib/store"
import { api } from "@/lib/api-client"
import { StatusBadge } from "@/components/status-badge"
import { Sparkles, Copy, Check, Hash, Shield, Loader2 } from "lucide-react"

const STEPS = [
  { value: "S0_intent", label: "S0 Intent", description: "Define objective and output contract." },
  { value: "S1_clarify", label: "S1 Clarify", description: "Clarify ambiguities and required fields." },
  { value: "S2_propose", label: "S2 Propose", description: "Propose extraction strategy and checks." },
  { value: "S3_execute", label: "S3 Execute", description: "Run extraction with final constraints." },
]

export function PromptTab() {
  const { activeProfileId, prompt, promptStatus, setPrompt, setPromptStatus } = useWorkspace()
  const [step, setStep] = useState("S3_execute")
  const [copied, setCopied] = useState(false)

  const handleGenerate = async () => {
    if (!activeProfileId) return
    setPromptStatus("running")
    try {
      const res = await api.generatePrompt(activeProfileId, step)
      setPrompt(res)
      setPromptStatus("done")
    } catch {
      setPromptStatus("failed")
    }
  }

  const handleCopy = async () => {
    if (!prompt?.prompt) return
    await navigator.clipboard.writeText(prompt.prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const activeStepMeta = STEPS.find((s) => s.value === step)

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">Prompt Generator</h2>
          <StatusBadge status={promptStatus} />
        </div>
      </div>

      {/* Step selector + generate */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Step pill group */}
          <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
            {STEPS.map((s) => (
              <button
                key={s.value}
                onClick={() => setStep(s.value)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  step === s.value
                    ? "bg-foreground text-background shadow-sm"
                    : "text-muted-foreground hover:bg-surface-inset hover:text-foreground"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          <button
            onClick={handleGenerate}
            disabled={promptStatus === "running" || !activeProfileId}
            className="btn-shimmer flex items-center gap-1.5 rounded-md bg-gradient-accent px-4 py-1.5 text-xs font-medium text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent disabled:opacity-50"
          >
            {promptStatus === "running" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            Generar
          </button>
        </div>

        {activeStepMeta && (
          <p className="text-[11px] text-muted-foreground">{activeStepMeta.description}</p>
        )}
      </div>

      {/* Prompt output */}
      {prompt && (
        <div className="space-y-4">
          {/* Metadata */}
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-inset px-2.5 py-1 text-[10px] font-mono text-muted-foreground">
              <Hash className="h-3 w-3" />
              {prompt.prompt_hash}
            </div>
            {prompt.constraints_embedded && (
              <div className="flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-inset px-2.5 py-1 text-[10px] text-muted-foreground">
                <Shield className="h-3 w-3" />
                Constraints embedded
              </div>
            )}
            <span className="text-[10px] text-muted-foreground/50">
              {prompt.prompt.length.toLocaleString()} chars
            </span>
          </div>

          {/* Prompt text */}
          <div className="group relative">
            <button
              onClick={handleCopy}
              className="absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-md border border-border bg-background/95 px-2.5 py-1.5 text-[10px] font-medium text-muted-foreground opacity-0 shadow-sm backdrop-blur-sm transition-all duration-200 group-hover:opacity-100 hover:text-foreground"
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3" />
                  Copiado
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  Copiar
                </>
              )}
            </button>
            <pre className="max-h-[500px] overflow-auto rounded-lg border border-border bg-surface-inset p-6 text-xs leading-relaxed text-foreground/80 whitespace-pre-wrap">
              {prompt.prompt}
            </pre>
          </div>
        </div>
      )}

      {!prompt && promptStatus === "draft" && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface py-24">
          <Sparkles className="mb-3 h-6 w-6 text-muted-foreground/30" />
          <p className="text-xs font-medium text-muted-foreground">
            Selecciona un step y genera el prompt
          </p>
          <p className="mt-1.5 text-[11px] text-muted-foreground/60">
            Cada step produce un prompt diferente optimizado para esa fase del pipeline
          </p>
        </div>
      )}
    </div>
  )
}
