"use client"

import { useEffect, useCallback, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useWorkspace } from "@/lib/store"
import { API_RUNTIME, api } from "@/lib/api-client"
import { FEATURE_FLAGS, WORKSPACE_TASK_ID } from "@/lib/contracts"
import type { Bundle, ProfileSummary } from "@/lib/contracts"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ProfileSelector } from "@/components/profile-selector"
import { ConfigTab } from "@/components/tabs/config-tab"
import { PromptTab } from "@/components/tabs/prompt-tab"
import { JsonlTab } from "@/components/tabs/jsonl-tab"
import { ResultsTab } from "@/components/tabs/results-tab"
import { CvTab } from "@/components/tabs/cv-tab"
import { StatusBadge } from "@/components/status-badge"
import { FadeIn, FloatingBlob, AnimatedTabContent } from "@/components/ui/motion"

export default function WorkspacePage() {
  const {
    profiles,
    setProfiles,
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
    bundleStatus,
    promptStatus,
    jsonlStatus,
    runStatus,
    cvStatus,
  } = useWorkspace()
  const [profilesLoadStatus, setProfilesLoadStatus] = useState<
    "loading" | "done" | "failed"
  >("loading")
  const loadBundle = useCallback(async (profileId: string) => {
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
  }, [
    setActiveProfile,
    setPrompt,
    setPromptStatus,
    setJsonl,
    setJsonlStatus,
    setJsonlRaw,
    setRun,
    setRunStatus,
    setCv,
    setCvStatus,
    setBundleStatus,
    setBundleErrors,
    setBundle,
  ])

  useEffect(() => {
    api.getProfiles()
      .then((p) => {
        const list = p as ProfileSummary[]
        setProfiles(list)
        if (list.length > 0 && !activeProfileId) {
          loadBundle(list[0].id)
        }
        setProfilesLoadStatus("done")
      })
      .catch(() => {
        setProfiles([])
        setProfilesLoadStatus("failed")
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const isLoading = profilesLoadStatus === "loading"

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      {/* Background blur — animated */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <FloatingBlob
          className="absolute -top-48 -right-48 h-[700px] w-[700px] rounded-full bg-foreground/[0.04] blur-3xl"
          duration={24}
          delay={0}
        />
        <FloatingBlob
          className="absolute -bottom-48 -left-48 h-[600px] w-[600px] rounded-full bg-foreground/[0.05] blur-3xl"
          duration={20}
          delay={3}
        />
      </div>

      {/* Header */}
      <FadeIn y={-10} delay={0.05} duration={0.4}>
        <header className="relative z-10 border-b glass shadow-elevation-sm">
          <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3 md:px-8">
            {/* Left: nav + branding */}
            <div className="flex items-center gap-3">
              <Link
                href="/"
                className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors duration-200 hover:text-foreground"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Inicio</span>
              </Link>
              <div className="h-4 w-px bg-border" />
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded bg-gradient-accent shadow-sm">
                  <span className="text-[9px] font-bold text-white tracking-tight">JS</span>
                </div>
                <span className="text-sm font-semibold tracking-tight text-foreground">Workspace</span>
              </div>
            </div>

            {/* Right: api badge + profile selector */}
            <div className="ml-auto flex items-center gap-3">
              <span className="hidden text-[10px] font-mono text-muted-foreground/50 sm:block">
                {API_RUNTIME.isMock ? `api: mock (${WORKSPACE_TASK_ID})` : `api: ${API_RUNTIME.base} (${WORKSPACE_TASK_ID})`}
              </span>
              <div className="h-4 w-px bg-border-subtle hidden sm:block" />
              <ProfileSelector />
            </div>
          </div>
        </header>
      </FadeIn>

      {/* Main */}
      <main className="relative z-10 mx-auto max-w-6xl px-6 py-8 md:px-8">
        {isLoading ? (
          <FadeIn>
            <div className="flex flex-col items-center justify-center py-36 text-center">
              <Loader2 className="mb-4 h-5 w-5 animate-spin text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">Cargando perfiles...</p>
            </div>
          </FadeIn>
        ) : profilesLoadStatus === "failed" ? (
          <FadeIn>
            <div className="flex flex-col items-center justify-center py-36 text-center">
              <p className="text-sm font-medium text-destructive">
                No se pudieron cargar los perfiles.
              </p>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Revisa conectividad/API y recarga la pagina.
              </p>
            </div>
          </FadeIn>
        ) : !activeProfileId ? (
          <FadeIn>
            <div className="flex flex-col items-center justify-center py-36 text-center">
              <div className="mb-5 h-12 w-12 rounded-xl border border-border bg-surface" />
              <p className="text-sm font-medium text-foreground">
                Selecciona un perfil para comenzar
              </p>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Usa el selector en la cabecera
              </p>
            </div>
          </FadeIn>
        ) : (
          <FadeIn delay={0.1}>
            <Tabs
              defaultValue="config"
              className="gap-0"
            >
              {/* Tab navigation — underline style */}
              <div className="mb-8 border-b border-border-subtle">
                <TabsList variant="underline">
                  <TabsTrigger value="config" variant="underline">
                    Configuracion
                    <StatusBadge status={bundleStatus} />
                  </TabsTrigger>
                  <TabsTrigger value="prompt" variant="underline">
                    Prompt
                    <StatusBadge status={promptStatus} />
                  </TabsTrigger>
                  <TabsTrigger value="jsonl" variant="underline">
                    JSONL
                    <StatusBadge status={jsonlStatus} />
                  </TabsTrigger>
                  <TabsTrigger value="results" variant="underline">
                    Resultados
                    <StatusBadge status={runStatus} />
                  </TabsTrigger>
                  {FEATURE_FLAGS.cv_enabled && (
                    <TabsTrigger value="cv" variant="underline">
                      CV
                      <StatusBadge status={cvStatus} />
                    </TabsTrigger>
                  )}
                </TabsList>
              </div>

              <TabsContent value="config" className="mt-0">
                <AnimatedTabContent tabKey="config">
                  <ConfigTab />
                </AnimatedTabContent>
              </TabsContent>
              <TabsContent value="prompt" className="mt-0">
                <AnimatedTabContent tabKey="prompt">
                  <PromptTab />
                </AnimatedTabContent>
              </TabsContent>
              <TabsContent value="jsonl" className="mt-0">
                <AnimatedTabContent tabKey="jsonl">
                  <JsonlTab />
                </AnimatedTabContent>
              </TabsContent>
              <TabsContent value="results" className="mt-0">
                <AnimatedTabContent tabKey="results">
                  <ResultsTab />
                </AnimatedTabContent>
              </TabsContent>
              {FEATURE_FLAGS.cv_enabled && (
                <TabsContent value="cv" className="mt-0">
                  <AnimatedTabContent tabKey="cv">
                    <CvTab />
                  </AnimatedTabContent>
                </TabsContent>
              )}
            </Tabs>
          </FadeIn>
        )}
      </main>
    </div>
  )
}
