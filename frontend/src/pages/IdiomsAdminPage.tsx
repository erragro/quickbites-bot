import { useMemo, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { toast } from "sonner"
import {
  Languages,
  Plus,
  Search,
  Trash2,
} from "lucide-react"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import {
  useCreateIdiom,
  useDeleteIdiom,
  useIdiomList,
  useUpdateIdiom,
  useUpsertIdiomTranslation,
} from "@/hooks/useIdioms"
import { humaniseError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  Idiom,
  IdiomCategory,
  TargetLanguage,
} from "@/types"


// Match the DB CHECK constraint on idiom_library.category (migration 007).
const CATEGORIES: { code: IdiomCategory; label: string; color: string }[] = [
  { code: "legal",   label: "Legal",   color: "bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-200" },
  { code: "work",    label: "Work",    color: "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200" },
  { code: "money",   label: "Money",   color: "bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-200" },
  { code: "general", label: "General", color: "bg-muted text-muted-foreground" },
  { code: "safety",  label: "Safety",  color: "bg-marigold-100 text-marigold-900 dark:bg-marigold-900/40 dark:text-marigold-100" },
]

// Match the DB CHECK constraint on idiom_translations.language. Order
// intentional: high-value languages first for the demo audience.
const LANGUAGES: { code: TargetLanguage; label: string; nativeLabel: string }[] = [
  { code: "hi", label: "Hindi",   nativeLabel: "हिन्दी" },
  { code: "bn", label: "Bengali", nativeLabel: "বাংলা" },
  { code: "ta", label: "Tamil",   nativeLabel: "தமிழ்" },
  { code: "te", label: "Telugu",  nativeLabel: "తెలుగు" },
  { code: "kn", label: "Kannada", nativeLabel: "ಕನ್ನಡ" },
  { code: "mr", label: "Marathi", nativeLabel: "मराठी" },
]


/**
 * Admin CRUD for the idiom library. Super-admin only (route gated
 * separately via ModuleGuard superAdminOnly).
 *
 * Layout: filter bar (search + category), then a card grid of idioms.
 * Each idiom card shows the source phrase, meaning, category badge,
 * and coloured dots for languages that have a translation. Click a
 * card to open the edit dialog, which handles both the idiom fields
 * and per-language translations in one modal.
 */
export function IdiomsAdminPage() {
  const list = useIdiomList()
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState<IdiomCategory | "all">("all")
  const [editing, setEditing] = useState<Idiom | null>(null)
  const [creating, setCreating] = useState(false)

  const filtered = useMemo(() => {
    if (!list.data) return []
    const q = search.trim().toLowerCase()
    return list.data.filter((i) => {
      if (category !== "all" && i.category !== category) return false
      if (!q) return true
      return (
        i.source_phrase.toLowerCase().includes(q) ||
        i.meaning.toLowerCase().includes(q)
      )
    })
  }, [list.data, search, category])

  if (list.isLoading) {
    return (
      <div className="grid h-full min-h-[50vh] place-items-center">
        <LoaderCircleIcon size={28} className="text-muted-foreground" animate animation="default" />
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24 }}
        className="mb-6 flex items-start justify-between gap-3"
      >
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Languages className="size-6 text-brand-600" />
            Idiom library
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Curated English phrases + their pre-verified equivalents in Hindi,
            Bengali, and other target languages. The translation pipeline
            substitutes these deterministically around Mayura so idioms
            never get literalised.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} className="gap-1.5">
          <Plus className="size-4" />
          Add idiom
        </Button>
      </motion.div>

      {/* Filters */}
      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-3 p-3">
          <div className="relative min-w-[240px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search phrase or meaning…"
              className="pl-8"
            />
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <CategoryChip
              label="All"
              active={category === "all"}
              onClick={() => setCategory("all")}
            />
            {CATEGORIES.map((c) => (
              <CategoryChip
                key={c.code}
                label={c.label}
                active={category === c.code}
                onClick={() => setCategory(c.code)}
              />
            ))}
          </div>
          <span className="ml-auto text-xs text-muted-foreground">
            {filtered.length} of {list.data?.length ?? 0}
          </span>
        </CardContent>
      </Card>

      {/* Grid */}
      {filtered.length === 0 ? (
        <Card className="border-dashed">
          <CardHeader className="text-center text-sm text-muted-foreground">
            No idioms match your filter.
          </CardHeader>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <AnimatePresence initial={false}>
            {filtered.map((idiom) => (
              <motion.div
                key={idiom.id}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.18 }}
              >
                <IdiomCard idiom={idiom} onClick={() => setEditing(idiom)} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {editing && (
        <IdiomDialog
          idiom={editing}
          open={true}
          onClose={() => setEditing(null)}
        />
      )}
      {creating && (
        <IdiomDialog
          idiom={null}
          open={true}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  )
}


// ---------- Card ----------


function IdiomCard({ idiom, onClick }: { idiom: Idiom; onClick: () => void }) {
  const catStyle = CATEGORIES.find((c) => c.code === idiom.category)?.color ?? ""
  const covered = new Set(idiom.translations.map((t) => t.language))
  return (
    <Card
      onClick={onClick}
      className={cn(
        "cursor-pointer transition-colors hover:border-brand-400/60 hover:shadow-md",
        !idiom.is_active && "opacity-60",
      )}
    >
      <CardContent className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{idiom.source_phrase}</div>
            <div className="line-clamp-2 text-xs text-muted-foreground">
              {idiom.meaning}
            </div>
          </div>
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
              catStyle,
            )}
          >
            {idiom.category}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {LANGUAGES.map((lang) => {
            const has = covered.has(lang.code)
            return (
              <span
                key={lang.code}
                title={has ? `${lang.label}: has translation` : `${lang.label}: missing`}
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  has
                    ? "bg-brand-600 text-white"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {lang.code}
              </span>
            )
          })}
          {!idiom.is_active && (
            <span className="ml-auto text-[10px] text-muted-foreground">
              inactive
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}


function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "border-brand-500 bg-brand-600 text-white"
          : "bg-background hover:bg-muted",
      )}
    >
      {label}
    </button>
  )
}


// ---------- Edit / Create Dialog ----------


function IdiomDialog({
  idiom,
  open,
  onClose,
}: {
  idiom: Idiom | null  // null = create mode
  open: boolean
  onClose: () => void
}) {
  const isEdit = idiom !== null
  const create = useCreateIdiom()
  const update = useUpdateIdiom()
  const del = useDeleteIdiom()
  const upsertTranslation = useUpsertIdiomTranslation()

  const [sourcePhrase, setSourcePhrase] = useState(idiom?.source_phrase ?? "")
  const [meaning, setMeaning] = useState(idiom?.meaning ?? "")
  const [category, setCategory] = useState<IdiomCategory>(idiom?.category ?? "general")
  const [isActive, setIsActive] = useState(idiom?.is_active ?? true)

  // Per-language draft translations (initialised from server state).
  // Only sent to the server when the user actually types something and
  // saves — untouched languages stay untouched.
  const [translationDrafts, setTranslationDrafts] = useState<Record<string, string>>(() => {
    const seed: Record<string, string> = {}
    idiom?.translations.forEach((t) => {
      seed[t.language] = t.translation
    })
    return seed
  })

  const anyPending =
    create.isPending || update.isPending || upsertTranslation.isPending

  const handleSave = async () => {
    try {
      if (isEdit && idiom) {
        // Only send fields that changed. Simplest heuristic: always send
        // all fields — the PATCH endpoint is idempotent.
        await update.mutateAsync({
          id: idiom.id,
          patch: {
            source_phrase: sourcePhrase.trim(),
            meaning: meaning.trim(),
            category,
            is_active: isActive,
          },
        })
        // Sync any changed translations serially so a failure surfaces
        // clearly rather than partially updating in parallel.
        for (const lang of LANGUAGES) {
          const draft = (translationDrafts[lang.code] ?? "").trim()
          const existing = idiom.translations.find((t) => t.language === lang.code)
          if (!draft && existing) {
            // Translation cleared — leave it (deleting is a separate
            // affordance if we add one later). For now empty draft ==
            // no change.
            continue
          }
          if (draft && draft !== (existing?.translation ?? "")) {
            await upsertTranslation.mutateAsync({
              idiomId: idiom.id,
              language: lang.code,
              translation: draft,
            })
          }
        }
        toast.success("Idiom saved")
      } else {
        // Create mode — send everything at once.
        const translations = LANGUAGES.filter((l) => (translationDrafts[l.code] ?? "").trim())
          .map((l) => ({
            language: l.code,
            translation: translationDrafts[l.code].trim(),
          }))
        await create.mutateAsync({
          source_phrase: sourcePhrase.trim(),
          meaning: meaning.trim(),
          category,
          is_active: isActive,
          translations,
        })
        toast.success("Idiom created")
      }
      onClose()
    } catch (err) {
      toast.error(humaniseError(err, "Save failed"))
    }
  }

  const handleDelete = async () => {
    if (!idiom) return
    if (!window.confirm(`Delete "${idiom.source_phrase}"? This can't be undone.`)) return
    try {
      await del.mutateAsync(idiom.id)
      toast.success("Deleted")
      onClose()
    } catch (err) {
      toast.error(humaniseError(err, "Delete failed"))
    }
  }

  const canSubmit =
    sourcePhrase.trim().length > 0 && meaning.trim().length > 0 && !anyPending

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit idiom" : "Add idiom"}</DialogTitle>
          <DialogDescription>
            English source + meaning gloss, then per-language equivalents.
            Empty translations stay untouched.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="idm-src">English phrase</Label>
              <Input
                id="idm-src"
                value={sourcePhrase}
                onChange={(e) => setSourcePhrase(e.target.value)}
                placeholder="e.g. at the end of the day"
                maxLength={200}
              />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="idm-meaning">Meaning (English gloss)</Label>
              <Textarea
                id="idm-meaning"
                value={meaning}
                onChange={(e) => setMeaning(e.target.value)}
                rows={2}
                placeholder="What this phrase actually means, in plain English."
                maxLength={1000}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="idm-cat">Category</Label>
              <select
                id="idm-cat"
                value={category}
                onChange={(e) => setCategory(e.target.value as IdiomCategory)}
                className="h-9 w-full rounded-md border bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.code} value={c.code}>{c.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-end gap-2">
              <div>
                <Label className="mb-1.5 block">Active</Label>
                <Switch
                  checked={isActive}
                  onCheckedChange={setIsActive}
                  aria-label="Active"
                />
              </div>
              <span className="pb-1 text-xs text-muted-foreground">
                {isActive ? "Detected in translations" : "Ignored by the scanner"}
              </span>
            </div>
          </div>

          <div className="border-t pt-3">
            <div className="mb-2 text-sm font-medium">Translations</div>
            <div className="space-y-2">
              {LANGUAGES.map((lang) => {
                const existing = idiom?.translations.find((t) => t.language === lang.code)
                return (
                  <div key={lang.code} className="flex items-start gap-2">
                    <div className="w-24 shrink-0 pt-2 text-xs">
                      <div className="font-medium">{lang.label}</div>
                      <div className="text-muted-foreground">{lang.nativeLabel}</div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <Input
                        value={translationDrafts[lang.code] ?? ""}
                        onChange={(e) =>
                          setTranslationDrafts((prev) => ({
                            ...prev,
                            [lang.code]: e.target.value,
                          }))
                        }
                        placeholder={
                          existing
                            ? "(edit)"
                            : `Add ${lang.label} translation`
                        }
                        className={cn(!existing && "text-muted-foreground placeholder:italic")}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <DialogFooter className="flex-row items-center">
          {isEdit && (
            <Button
              variant="ghost"
              onClick={handleDelete}
              disabled={del.isPending}
              className="mr-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          )}
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSubmit}>
            {anyPending ? "Saving…" : isEdit ? "Save changes" : "Add idiom"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
