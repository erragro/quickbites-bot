import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { motion } from "motion/react"
import { toast } from "sonner"
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Info,
  Loader2,
  ShieldCheck,
} from "lucide-react"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useContract, useReprocessContract } from "@/hooks/useContracts"
import { humaniseError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ContractStatus } from "@/types"


type Risk = "red" | "amber" | "green"

interface Clause {
  id: string
  heading: string | null
  section_number: string | null
  text: string
}

interface Annotation {
  clause_id: string
  risk: Risk
  statute: string | null
  note: string
}

interface Rendered {
  clause_id: string
  explanation: string
  implication: string
  action: string | null
}


/**
 * Contract detail viewer.
 *
 * Shows a clause-by-clause breakdown. Each card joins:
 *  - clauses[]     from stages.stage_1
 *  - annotations[] from stages.stage_2
 *  - rendered[]    from stages.stage_3
 *
 * Colour semantics (from tone spec):
 *  - red   Adverse. Show the clause, show what's problematic, propose an action.
 *  - amber Worth knowing. Show the clause, explain it neutrally.
 *  - green Favourable or boilerplate. Show the clause with a light touch.
 *
 * When the contract is still processing (status != 'ready'/'failed'),
 * the page polls the detail endpoint every 2s via useContract's
 * refetchInterval — the loading state below transitions on its own.
 */
export function ContractDetailPage() {
  const { contractId } = useParams<{ contractId: string }>()
  const { data: contract, isLoading, error } = useContract(contractId)
  const reprocess = useReprocessContract()

  const onRead = async () => {
    if (!contractId) return
    try {
      await reprocess.mutateAsync(contractId)
      toast.success("Reading started")
    } catch (err) {
      toast.error(humaniseError(err, "Could not start reading"))
    }
  }

  if (isLoading) {
    return (
      <div className="grid h-full min-h-[50vh] place-items-center">
        <LoaderCircleIcon size={28} className="text-muted-foreground" animate animation="default" />
      </div>
    )
  }

  if (error || !contract) {
    return (
      <div className="mx-auto w-full max-w-4xl px-6 py-8">
        <BackLink />
        <Card className="mt-4">
          <CardContent className="p-6 text-sm text-destructive">
            Contract not found. It may have been deleted.
          </CardContent>
        </Card>
      </div>
    )
  }

  const stages = (contract.stages ?? {}) as {
    stage_1?: { clauses?: Clause[]; contract_type?: string; confidence?: number }
    stage_2?: { annotations?: Annotation[]; error?: string | null }
    stage_3?: {
      rendered?: Rendered[]  // always English (Gemini)
      error?: string | null
      translation?: {
        language: string
        // Present when Mayura translated the English source. When null
        // (translation failed), we fall back to the English rendered.
        rendered: Rendered[] | null
        translator?: string
        error?: string | null
      }
    }
  }

  const clauses = stages.stage_1?.clauses ?? []
  const annotationsById = new Map(
    (stages.stage_2?.annotations ?? []).map((a) => [a.clause_id, a]),
  )

  // Prefer the Mayura translation when it's present and populated.
  // Falls back to Stage 3's English source when: target_language is 'en',
  // translation is missing, or translation failed (rendered = null).
  const translation = stages.stage_3?.translation
  const usingTranslation = Boolean(
    translation && translation.rendered && translation.rendered.length > 0,
  )
  const displayedRendered = usingTranslation
    ? translation!.rendered!
    : (stages.stage_3?.rendered ?? [])
  const renderedById = new Map(
    displayedRendered.map((r) => [r.clause_id, r]),
  )

  const isProcessing = contract.status !== "ready" && contract.status !== "failed"
  const isFailed = contract.status === "failed"

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <BackLink />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24 }}
        className="mt-4"
      >
        <div className="flex items-start gap-3">
          <div className="grid size-11 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
            <FileText className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-bold tracking-tight">
              {contract.filename}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {contract.contract_type && (
                <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-800 dark:bg-brand-900/40 dark:text-brand-200">
                  {contract.contract_type}
                </span>
              )}
              {contract.language && (
                <span className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider">
                  Detected: {contract.language}
                </span>
              )}
              <span>{formatSize(contract.size_bytes)}</span>
              <span>·</span>
              <span>Uploaded {new Date(contract.created_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
      </motion.div>

      {contract.status === "uploaded" && (
        <Card className="mt-6 border-brand-200 bg-brand-50/40 dark:border-brand-900/40 dark:bg-brand-900/10">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <div className="flex items-center gap-2">
              <BookOpen className="size-4 text-brand-600" />
              <span>Ready to read. This will take about 30 to 90 seconds.</span>
            </div>
            <Button onClick={onRead} disabled={reprocess.isPending} className="gap-1.5">
              <BookOpen className="size-4" />
              {reprocess.isPending ? "Starting…" : "Read this contract"}
            </Button>
          </CardContent>
        </Card>
      )}

      {isProcessing && (
        <ProgressCard
          status={contract.status}
          startedAt={contract.updated_at}
          isTranslating={contract.target_language !== "en"}
        />
      )}

      {isFailed && (
        <Card className="mt-6 border-red-200 bg-red-50/60 dark:border-red-900/40 dark:bg-red-950/40">
          <CardContent className="p-4 text-sm">
            <div className="mb-1 flex items-center gap-2 font-medium text-red-800 dark:text-red-200">
              <AlertTriangle className="size-4" />
              Analysis failed
            </div>
            <p className="text-red-700 dark:text-red-300">
              {contract.error_message ??
                "Something went wrong. Try uploading again with a clearer photo or PDF."}
            </p>
          </CardContent>
        </Card>
      )}

      {(stages.stage_1 as { error?: string | null })?.error && (
        <NoteBanner tone="amber">
          We had trouble reading this contract:{" "}
          {(stages.stage_1 as { error?: string | null }).error}
          {" — try uploading a clearer copy of the contract."}
        </NoteBanner>
      )}
      {stages.stage_2?.error && (
        <NoteBanner tone="amber">
          Statute annotations were partial: {stages.stage_2.error}
        </NoteBanner>
      )}
      {stages.stage_3?.error && (
        <NoteBanner tone="amber">
          Plain-language rendering was partial: {stages.stage_3.error}
        </NoteBanner>
      )}
      {contract.target_language !== "en" && translation?.error && !usingTranslation && (
        <NoteBanner tone="amber">
          We could not translate the analysis into {contract.target_language.toUpperCase()}
          right now: {translation.error}. Showing the English source below.
        </NoteBanner>
      )}
      {usingTranslation && (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-brand-200 bg-brand-50/60 px-3 py-2 text-xs text-brand-800 dark:border-brand-900/40 dark:bg-brand-900/20 dark:text-brand-200">
          <Info className="size-3.5 shrink-0" />
          <span>
            Analysis translated into {contract.target_language.toUpperCase()} by Sarvam Mayura.
            Original clause text on each card is kept in the language it was written.
          </span>
        </div>
      )}

      {clauses.length > 0 && (
        <div className="mt-6">
          <RiskSummary annotations={stages.stage_2?.annotations ?? []} />
        </div>
      )}

      {clauses.length > 0 ? (
        <div className="mt-4 space-y-3">
          {clauses.map((clause) => (
            <ClauseCard
              key={clause.id}
              clause={clause}
              annotation={annotationsById.get(clause.id)}
              rendered={renderedById.get(clause.id)}
            />
          ))}
        </div>
      ) : (
        !isProcessing && !isFailed && (
          <Card className="mt-6 border-dashed">
            <CardContent className="p-6 text-center text-sm text-muted-foreground">
              No clauses were extracted from this contract.
            </CardContent>
          </Card>
        )
      )}

      <p className="mt-10 border-t pt-6 text-xs text-muted-foreground">
        Sreshtha is information, not legal advice. For formal help, call
        India Labourline at <span className="font-medium">1800-419-1550</span>.
      </p>
    </div>
  )
}


// ---------- Progress card (step indicators + elapsed timer) ----------


type ProgressStepState = "done" | "active" | "pending"

interface ProgressStep {
  key: string
  label: string
  state: ProgressStepState
}


function stepsFor(
  status: ContractStatus,
  isTranslating: boolean,
): ProgressStep[] {
  // Order of the pipeline: read → understand → analyse → translate → done.
  // Translate step only shown when target_language != 'en'; otherwise
  // Stage 3's English output is already the final rendition.
  const order = isTranslating
    ? ["read", "understand", "analyse", "translate"]
    : ["read", "understand", "analyse"]

  // Map row status to which step is currently active.
  const activeByStatus: Partial<Record<ContractStatus, string>> = {
    ocr_pending: "read",
    ocr_done: "understand",
    processing: isTranslating ? "translate" : "analyse",
  }
  const currentKey = activeByStatus[status] ?? order[0]
  const currentIdx = order.indexOf(currentKey)

  const label: Record<string, string> = {
    read: "Reading the contract",
    understand: "Understanding clauses",
    analyse: "Analysing risks",
    translate: "Translating for you",
  }

  return order.map((k, i) => ({
    key: k,
    label: label[k] ?? k,
    state: i < currentIdx ? "done" : i === currentIdx ? "active" : "pending",
  }))
}


function useElapsedSeconds(startedIso: string): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const startedAt = new Date(startedIso).getTime()
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}


function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}


function ProgressCard({
  status,
  startedAt,
  isTranslating,
}: {
  status: ContractStatus
  startedAt: string
  isTranslating: boolean
}) {
  const elapsed = useElapsedSeconds(startedAt)
  const steps = stepsFor(status, isTranslating)

  return (
    <Card className="mt-6 border-brand-200 bg-brand-50/60 dark:border-brand-900/40 dark:bg-brand-900/20">
      <CardHeader className="flex flex-row items-center justify-between gap-3 pb-2">
        <div className="flex items-center gap-2 font-medium">
          <Loader2 className="size-4 animate-spin text-brand-600" />
          Reading your contract
        </div>
        <div
          className="font-mono text-sm tabular-nums text-brand-700 dark:text-brand-200"
          aria-label={`Elapsed ${elapsed} seconds`}
        >
          {formatElapsed(elapsed)}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ol className="space-y-2">
          {steps.map((step) => (
            <li key={step.key} className="flex items-center gap-3 text-sm">
              <StepIcon state={step.state} />
              <span
                className={cn(
                  step.state === "done" && "text-muted-foreground line-through",
                  step.state === "active" && "font-medium text-foreground",
                  step.state === "pending" && "text-muted-foreground",
                )}
              >
                {step.label}
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-muted-foreground">
          First-time reads for a new language take up to 2 minutes while
          the reader loads. Later reads in the same language are much faster.
        </p>
      </CardContent>
    </Card>
  )
}


function StepIcon({ state }: { state: ProgressStepState }) {
  if (state === "done") {
    return (
      <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand-600 text-white">
        <Check className="size-3" />
      </span>
    )
  }
  if (state === "active") {
    return (
      <span className="grid size-5 shrink-0 place-items-center rounded-full border-2 border-brand-600 bg-white dark:bg-brand-950">
        <Loader2 className="size-3 animate-spin text-brand-600" />
      </span>
    )
  }
  return (
    <span className="grid size-5 shrink-0 place-items-center rounded-full border-2 border-muted-foreground/30 bg-transparent" />
  )
}


function BackLink() {
  return (
    <Link
      to="/contracts"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-brand-600"
    >
      <ArrowLeft className="size-4" />
      All contracts
    </Link>
  )
}


// ---------- Risk summary bar ----------


function RiskSummary({ annotations }: { annotations: Annotation[] }) {
  const counts = { red: 0, amber: 0, green: 0 }
  for (const a of annotations) counts[a.risk] += 1
  const total = counts.red + counts.amber + counts.green
  if (total === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/40 px-4 py-3 text-sm">
      <span className="font-medium">At a glance:</span>
      {counts.red > 0 && (
        <RiskBadge risk="red">{counts.red} adverse</RiskBadge>
      )}
      {counts.amber > 0 && (
        <RiskBadge risk="amber">{counts.amber} worth knowing</RiskBadge>
      )}
      {counts.green > 0 && (
        <RiskBadge risk="green">{counts.green} favourable</RiskBadge>
      )}
    </div>
  )
}


// ---------- Clause card ----------


function ClauseCard({
  clause,
  annotation,
  rendered,
}: {
  clause: Clause
  annotation: Annotation | undefined
  rendered: Rendered | undefined
}) {
  const [showOriginal, setShowOriginal] = useState(false)
  const risk = annotation?.risk ?? "amber"

  return (
    <Card
      className={cn(
        "border-l-4",
        RISK_BORDER[risk],
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {clause.section_number && (
              <span className="font-mono font-medium text-foreground">
                {clause.section_number}
              </span>
            )}
            {clause.heading && (
              <span className="truncate uppercase tracking-wide">
                {clause.heading}
              </span>
            )}
          </div>
          {rendered?.explanation ? (
            <div className="mt-1 text-sm font-medium leading-snug text-foreground">
              {rendered.explanation}
            </div>
          ) : (
            <div className="mt-1 text-sm italic text-muted-foreground">
              No plain-language rendering available.
            </div>
          )}
        </div>
        <RiskBadge risk={risk}>{RISK_LABEL[risk]}</RiskBadge>
      </CardHeader>

      <CardContent className="space-y-3 pt-0 text-sm">
        {rendered?.implication && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">
              What this means for you:
            </span>{" "}
            {rendered.implication}
          </p>
        )}

        {rendered?.action && (
          <div className="flex items-start gap-2 rounded-md bg-marigold-50 px-3 py-2 text-marigold-900 dark:bg-marigold-900/30 dark:text-marigold-100">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
            <div>
              <span className="font-medium">Suggested action: </span>
              {rendered.action}
            </div>
          </div>
        )}

        {annotation && (annotation.statute || annotation.note) && (
          <div className="flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <div className="min-w-0 flex-1">
              {annotation.statute && (
                <div className="font-medium text-foreground">
                  {annotation.statute}
                </div>
              )}
              {annotation.note && <div className="mt-0.5">{annotation.note}</div>}
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowOriginal((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-brand-600"
        >
          {showOriginal ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
          {showOriginal ? "Hide" : "Show"} original clause
        </button>
        {showOriginal && (
          <div className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-mono text-xs text-foreground">
            {clause.text}
          </div>
        )}
      </CardContent>
    </Card>
  )
}


// ---------- Style tables ----------


const RISK_BORDER: Record<Risk, string> = {
  red: "border-l-red-500",
  amber: "border-l-marigold-500",
  green: "border-l-green-500",
}

const RISK_LABEL: Record<Risk, string> = {
  red: "Adverse",
  amber: "Worth knowing",
  green: "Favourable",
}

const RISK_PILL: Record<Risk, string> = {
  red: "bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-200",
  amber: "bg-marigold-100 text-marigold-900 dark:bg-marigold-900/40 dark:text-marigold-100",
  green: "bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-200",
}

function RiskBadge({
  risk,
  children,
}: {
  risk: Risk
  children: React.ReactNode
}) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
        RISK_PILL[risk],
      )}
    >
      {children}
    </span>
  )
}


function NoteBanner({
  tone,
  children,
}: {
  tone: "amber"
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        "mt-4 flex items-start gap-2 rounded-md border px-3 py-2 text-xs",
        tone === "amber"
          ? "border-marigold-200 bg-marigold-50 text-marigold-900 dark:border-marigold-900/40 dark:bg-marigold-950/40 dark:text-marigold-200"
          : "",
      )}
    >
      <Info className="mt-0.5 size-3.5 shrink-0" />
      <div>{children}</div>
    </div>
  )
}


// ---------- Utilities ----------


function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}


// Status typing kept exported so ContractReaderPage can share the type
// signature if it wants to render the same badge inline later.
export type { ContractStatus }
