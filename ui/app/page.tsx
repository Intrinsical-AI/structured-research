"use client"

import Link from "next/link"
import { ArrowRight, Settings2, FileText, FileCheck, BarChart3, FileOutput } from "lucide-react"
import { API_RUNTIME } from "@/lib/api-client"
import { FadeIn, StaggerList, StaggerItem, FloatingBlob } from "@/components/ui/motion"

const steps = [
  {
    number: "01",
    title: "Configurar",
    description: "Define perfil, constraints y modelo de scoring. Validacion dual JSON + Form.",
    icon: Settings2,
  },
  {
    number: "02",
    title: "Prompt",
    description: "Genera prompts optimizados por step (S1-S4) con constraints embebidas y hash.",
    icon: FileText,
  },
  {
    number: "03",
    title: "JSONL",
    description: "Carga datos JSONL. Validacion incremental por linea, tolerante a errores parciales.",
    icon: FileCheck,
  },
  {
    number: "04",
    title: "Scoring",
    description: "Gate filters + weighted scoring. Tabla filtrable con metricas ETL y anomalias.",
    icon: BarChart3,
  },
  {
    number: "05",
    title: "CV",
    description: "Genera CV adaptado a la oferta seleccionada. Preview + export markdown.",
    icon: FileOutput,
  },
]

export default function LandingPage() {
  const modeLabel = API_RUNTIME.isMock ? "Demo Mode / Mock API" : "Live Mode / FastAPI"

  return (
    <main className="relative min-h-screen bg-background text-foreground overflow-hidden">
      {/* Background blur — animated blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <FloatingBlob
          className="absolute -top-40 -left-40 h-[500px] w-[500px] rounded-full bg-foreground/[0.06] blur-3xl"
          duration={22}
          delay={0}
        />
        <FloatingBlob
          className="absolute top-1/3 -right-52 h-[600px] w-[600px] rounded-full bg-foreground/[0.04] blur-3xl"
          duration={26}
          delay={2}
        />
        <FloatingBlob
          className="absolute -bottom-32 left-1/4 h-[400px] w-[400px] rounded-full bg-foreground/[0.05] blur-3xl"
          duration={20}
          delay={4}
        />
        <FloatingBlob
          className="absolute top-2/3 left-2/3 h-[300px] w-[300px] rounded-full bg-foreground/[0.03] blur-3xl"
          duration={24}
          delay={1}
        />
      </div>

      {/* Nav */}
      <FadeIn delay={0.1} y={-10}>
        <nav className="relative z-10 flex items-center justify-between px-6 py-5 md:px-12 lg:px-20">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-gradient-accent shadow-sm">
              <span className="text-[10px] font-bold text-white tracking-tight">JS</span>
            </div>
            <span className="text-sm font-semibold tracking-tight text-foreground">Job Search</span>
          </div>
          <Link
            href="/workspace"
            className="group flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors duration-200 hover:text-foreground"
          >
            Workspace
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </Link>
        </nav>
      </FadeIn>

      {/* Hero */}
      <section className="relative z-10 flex flex-col items-center px-6 pt-24 pb-20 text-center md:pt-36 md:pb-28 lg:px-20">
        {/* Mode pill */}
        <FadeIn delay={0.2}>
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border glass px-3.5 py-1.5 text-[11px] font-medium text-muted-foreground shadow-elevation-sm">
            <span className="flex h-1.5 w-1.5 rounded-full bg-gradient-accent animate-pulse" />
            {modeLabel}
          </div>
        </FadeIn>

        <FadeIn delay={0.35} duration={0.7}>
          <h1 className="max-w-3xl text-4xl font-bold tracking-tight text-foreground md:text-6xl lg:text-7xl text-balance leading-[1.06]">
            <span className="text-gradient-accent">Structured</span>
            <br />
            Job Search
          </h1>
        </FadeIn>

        <FadeIn delay={0.5}>
          <p className="mt-7 max-w-md text-[15px] text-muted-foreground leading-relaxed text-pretty">
            Pipeline completo: configuracion de perfil, generacion de prompts, validacion JSONL, scoring con gates y generacion de CV. Todo trazable, todo estructurado.
          </p>
        </FadeIn>

        <FadeIn delay={0.65}>
          <div className="mt-10 flex items-center gap-4">
            <Link
              href="/workspace"
              className="btn-shimmer inline-flex items-center gap-2 rounded-lg bg-gradient-accent px-6 py-2.5 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:bg-gradient-accent-hover hover:shadow-lg glow-accent active:scale-[0.98]"
            >
              Ir a Workspace
              <ArrowRight className="h-4 w-4" />
            </Link>
            <span className="text-xs text-muted-foreground/60">
              Perfil auto-cargado
            </span>
          </div>
        </FadeIn>
      </section>

      {/* Steps Grid */}
      <section className="relative z-10 px-6 pb-28 md:px-12 lg:px-20">
        <div className="mx-auto max-w-5xl">
          <FadeIn delay={0.7}>
            <p className="mb-8 text-center text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50">
              Pipeline en 5 pasos
            </p>
          </FadeIn>
          <StaggerList className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
            {steps.map((step) => (
              <StaggerItem key={step.number}>
                <div
                  className="group relative rounded-xl border border-border bg-gradient-surface p-5 shadow-elevation-xs transition-all duration-300 hover:border-foreground/20 hover:shadow-elevation-md hover:bg-background"
                >
                  <div className="mb-4 flex items-center justify-between">
                    <span className="font-mono text-[10px] text-muted-foreground/50">{step.number}</span>
                    <step.icon className="h-4 w-4 text-muted-foreground/40 transition-colors duration-200 group-hover:text-foreground/60" />
                  </div>
                  <h3 className="mb-1.5 text-sm font-semibold text-foreground">{step.title}</h3>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">{step.description}</p>
                </div>
              </StaggerItem>
            ))}
          </StaggerList>
        </div>
      </section>

      {/* Footer */}
      <FadeIn delay={0.9}>
        <footer className="relative z-10 border-t border-border px-6 py-5 md:px-12 lg:px-20">
          <div className="flex items-center justify-between text-[10px] text-muted-foreground/50">
            <span>Job Search MVP</span>
            <span className="font-mono">v0.1.0</span>
          </div>
        </footer>
      </FadeIn>
    </main>
  )
}
