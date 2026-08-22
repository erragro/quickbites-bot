import { useRef, useState } from "react"
import { Link } from "react-router-dom"
import { motion, AnimatePresence } from "motion/react"
import { toast } from "sonner"
import {
  BookOpen,
  ChevronRight,
  FileText,
  Languages,
  Loader2,
  RotateCw,
  Trash2,
  UploadCloud,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  useContractList,
  useDeleteContract,
  useReprocessContract,
  useUploadContract,
} from "@/hooks/useContracts"
import { humaniseError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ContractStatus, ContractSummary, TargetLanguage, TargetScript, TranslationMode } from "@/types"


const MAX_MB = 10
const ACCEPTED = ".pdf,.jpg,.jpeg,.png"

// Order is intentional: Hindi first (broadest reach for Indian gig
// workers), then Bengali (migrant workforce across cities the PRD calls
// out), then Tamil, then the rest. English last — it's a fallback for
// this audience, not the default.
const LANGUAGE_OPTIONS: { code: TargetLanguage; label: string; nativeLabel: string }[] = [
  { code: "hi", label: "Hindi",   nativeLabel: "हिन्दी" },
  { code: "bn", label: "Bengali", nativeLabel: "বাংলা" },
  { code: "ta", label: "Tamil",   nativeLabel: "தமிழ்" },
  { code: "te", label: "Telugu",  nativeLabel: "తెలుగు" },
  { code: "kn", label: "Kannada", nativeLabel: "ಕನ್ನಡ" },
  { code: "mr", label: "Marathi", nativeLabel: "मराठी" },
  { code: "en", label: "English", nativeLabel: "English" },
]

// Languages whose native scripts have a widely-used Roman/Latin
// transliteration alternative that many workers actually read more
// fluently. Only show the script toggle for these.
const SCRIPT_TOGGLE_LANGUAGES: ReadonlySet<TargetLanguage> = new Set(["hi", "bn", "mr"])

// Sarvam Mayura tone/register modes. Labels + hints match the
// thought-translate project verbatim so a worker moving between the
// two apps sees identical framing. Default is 'formal' — a worker
// picking Hindi as output should get actual Hindi, not Hinglish,
// unless they opt in.
const TRANSLATION_MODE_OPTIONS: {
  code: TranslationMode
  label: string
  hint: string
}[] = [
  {
    code: "formal",
    label: "Formal",
    hint: "Polite, standard tone. Best for official or legal text.",
  },
  {
    code: "modern-colloquial",
    label: "Modern colloquial",
    hint: "Casual, everyday spoken style.",
  },
  {
    code: "classic-colloquial",
    label: "Classic colloquial",
    hint: "Traditional everyday spoken style.",
  },
  {
    code: "code-mixed",
    label: "Code-mixed (Hinglish / Benglish)",
    hint: "Mixes in common English words, the way people actually talk on WhatsApp.",
  },
]


/**
 * Contract Reader landing page.
 *
 * Day 4 scope: upload + list + delete only. Day 5-8 layer on:
 *   - clicking a row opens a viewer with clause-by-clause explanation
 *   - status pill polls until 'ready' or 'failed'
 *   - re-process button on 'failed' rows
 *
 * Upload UX is drag-drop with click-to-select fallback. Client-side
 * validation mirrors the backend's whitelist so a bad choice is caught
 * before the round trip; a friendly error toast surfaces server-side
 * rejections (which will be identical text since we share the copy).
 */
export function ContractReaderPage() {
  const list = useContractList()
  const upload = useUploadContract()
  const del = useDeleteContract()
  const reprocess = useReprocessContract()

  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  // Worker's chosen output language. Persisted per-page-view so a burst
  // of uploads doesn't force re-picking every time. Defaults to Hindi
  // because it's the widest-reach language in the target audience.
  const [targetLanguage, setTargetLanguage] = useState<TargetLanguage>("hi")
  // Script toggle: only meaningful for a few Indic languages where Roman
  // transliteration is common. Server ignores it when target == 'en'.
  const [targetScript, setTargetScript] = useState<TargetScript>("native")
  // Mayura register/tone. Default 'formal' — pure Hindi/Bengali/etc.
  // Explicit opt-in for Hinglish-style code-mixing.
  const [translationMode, setTranslationMode] = useState<TranslationMode>("formal")

  const showScriptToggle = SCRIPT_TOGGLE_LANGUAGES.has(targetLanguage)
  const showModeSelector = targetLanguage !== "en"

  const handleFiles = async (files: FileList | File[] | null) => {
    if (!files || files.length === 0) return
    const file = files[0]

    // Client-side gate — server also enforces both.
    if (file.size > MAX_MB * 1024 * 1024) {
      toast.error(`File too large. Max ${MAX_MB} MB.`)
      return
    }
    const okMimes = ["application/pdf", "image/jpeg", "image/png"]
    if (!okMimes.includes(file.type)) {
      toast.error("Please upload a PDF, JPG, or PNG.")
      return
    }

    try {
      await upload.mutateAsync({
        file,
        targetLanguage,
        targetScript: showScriptToggle ? targetScript : "native",
        translationMode: showModeSelector ? translationMode : "formal",
      })
      toast.success(`Uploaded ${file.name}`)
    } catch (err) {
      toast.error(humaniseError(err, "Could not upload"))
    } finally {
      // Reset the input so re-uploading the same file fires onChange.
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const onDelete = async (row: ContractSummary) => {
    try {
      await del.mutateAsync(row.id)
      toast.success(`Deleted ${row.filename}`)
    } catch (err) {
      toast.error(humaniseError(err, "Could not delete"))
    }
  }

  const onReprocess = async (row: ContractSummary) => {
    try {
      await reprocess.mutateAsync(row.id)
      toast.success(`Retrying ${row.filename}`)
    } catch (err) {
      toast.error(humaniseError(err, "Could not restart processing"))
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <FileText className="size-6 text-brand-600" />
          Contract Reader
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Upload the contract you signed with your platform. We'll break it down
          clause by clause and flag anything worth knowing, in your language.
        </p>
      </motion.div>

      {/* Language selector — MUST be picked before upload. The whole
          product hinges on workers getting output in their language;
          burying this in an "Advanced" collapse would defeat that. */}
      <Card className="mb-3">
        <CardContent className="flex flex-wrap items-center gap-4 p-4 text-sm">
          <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
            <Languages className="size-4" />
            <span>Explain this contract in</span>
          </div>
          <select
            value={targetLanguage}
            onChange={(e) => setTargetLanguage(e.target.value as TargetLanguage)}
            aria-label="Output language"
            className={cn(
              "h-9 rounded-md border bg-background px-2 text-sm font-medium",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400",
            )}
          >
            {LANGUAGE_OPTIONS.map((opt) => (
              <option key={opt.code} value={opt.code}>
                {opt.label} · {opt.nativeLabel}
              </option>
            ))}
          </select>

          {showScriptToggle && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Script:
              </span>
              <div className="inline-flex overflow-hidden rounded-md border">
                <button
                  type="button"
                  onClick={() => setTargetScript("native")}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium transition-colors",
                    targetScript === "native"
                      ? "bg-brand-600 text-white"
                      : "bg-background hover:bg-muted",
                  )}
                >
                  Native
                </button>
                <button
                  type="button"
                  onClick={() => setTargetScript("roman")}
                  className={cn(
                    "border-l px-3 py-1.5 text-xs font-medium transition-colors",
                    targetScript === "roman"
                      ? "bg-brand-600 text-white"
                      : "bg-background hover:bg-muted",
                  )}
                >
                  Roman
                </button>
              </div>
            </div>
          )}

          {showModeSelector && (
            <div className="flex w-full flex-col gap-1.5 border-t pt-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Tone:</span>
                <span className="text-[10px]">
                  How much English should stay in the output?
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {TRANSLATION_MODE_OPTIONS.map((opt) => {
                  const selected = translationMode === opt.code
                  return (
                    <button
                      key={opt.code}
                      type="button"
                      onClick={() => setTranslationMode(opt.code)}
                      title={opt.hint}
                      className={cn(
                        "flex flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left text-xs transition-colors",
                        selected
                          ? "border-brand-500 bg-brand-50 text-brand-900 dark:bg-brand-900/30 dark:text-brand-100"
                          : "hover:bg-muted",
                      )}
                    >
                      <span className="font-medium">{opt.label}</span>
                      <span className="text-[10px] text-muted-foreground leading-tight">
                        {opt.hint}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upload zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 transition-colors",
          isDragging
            ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
            : "border-muted-foreground/30 hover:border-brand-400 hover:bg-muted/40",
          upload.isPending && "pointer-events-none opacity-70",
        )}
      >
        <div className="grid size-12 place-items-center rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
          {upload.isPending ? (
            <Loader2 className="size-6 animate-spin" />
          ) : (
            <UploadCloud className="size-6" />
          )}
        </div>
        <div className="text-sm font-medium">
          {upload.isPending
            ? "Uploading…"
            : "Drop a contract here, or click to choose a file"}
        </div>
        <div className="text-xs text-muted-foreground">
          PDF, JPG, or PNG. Max {MAX_MB} MB.
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* List */}
      <div className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">
            Your contracts
          </h2>
          {list.data && (
            <span className="text-xs text-muted-foreground">
              {list.data.length} {list.data.length === 1 ? "file" : "files"}
            </span>
          )}
        </div>

        {list.isLoading ? (
          <Card className="grid h-24 place-items-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </Card>
        ) : list.data && list.data.length > 0 ? (
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <ul className="divide-y">
                <AnimatePresence initial={false}>
                  {list.data.map((row) => (
                    <motion.li
                      key={row.id}
                      layout
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -12 }}
                      transition={{ duration: 0.18 }}
                      className="group flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-muted/40"
                    >
                      <Link
                        to={`/contracts/${row.id}`}
                        className="flex min-w-0 flex-1 items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:rounded-md"
                      >
                        <ContractIcon mime={row.mime_type} />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium group-hover:text-brand-700 dark:group-hover:text-brand-300">
                            {row.filename}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {formatSize(row.size_bytes)} · uploaded{" "}
                            {new Date(row.created_at).toLocaleString()}
                          </div>
                        </div>
                        <ChevronRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                      </Link>
                      <StatusPill status={row.status} />
                      {row.status === "uploaded" && (
                        <Button
                          size="sm"
                          onClick={() => onReprocess(row)}
                          disabled={reprocess.isPending}
                          className="gap-1.5"
                        >
                          <BookOpen className="size-4" />
                          Read this contract
                        </Button>
                      )}
                      {row.status === "failed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onReprocess(row)}
                          disabled={reprocess.isPending}
                          aria-label={`Retry ${row.filename}`}
                          className="text-muted-foreground hover:text-brand-600"
                        >
                          <RotateCw className="size-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onDelete(row)}
                        disabled={del.isPending}
                        aria-label={`Delete ${row.filename}`}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-dashed">
            <CardHeader className="text-center text-sm text-muted-foreground">
              No contracts uploaded yet. Drop your first one above.
            </CardHeader>
          </Card>
        )}
      </div>

      <div className="mt-12 border-t pt-6 text-xs text-muted-foreground">
        We read what you upload; we don't send it anywhere. Files are stored
        against your account only.
      </div>
    </div>
  )
}


function ContractIcon({ mime }: { mime: string }) {
  return (
    <div className="grid size-9 shrink-0 place-items-center rounded-md bg-muted/50">
      {mime === "application/pdf" ? (
        <FileText className="size-4 text-muted-foreground" />
      ) : (
        <FileText className="size-4 text-muted-foreground" />
      )}
    </div>
  )
}


const STATUS_STYLES: Record<ContractStatus, string> = {
  uploaded: "bg-muted text-muted-foreground",
  ocr_pending: "bg-marigold-100 text-marigold-800 dark:bg-marigold-900/40 dark:text-marigold-200",
  ocr_done: "bg-marigold-100 text-marigold-800 dark:bg-marigold-900/40 dark:text-marigold-200",
  processing: "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200",
  ready: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
}

const STATUS_LABEL: Record<ContractStatus, string> = {
  uploaded: "Ready to read",
  ocr_pending: "Reading…",
  ocr_done: "Understanding…",
  processing: "Analysing…",
  ready: "Ready",
  failed: "Failed",
}

function StatusPill({ status }: { status: ContractStatus }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
        STATUS_STYLES[status],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}


function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
