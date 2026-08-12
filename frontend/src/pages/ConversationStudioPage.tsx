import { useMemo, useState } from "react"
import { motion } from "motion/react"
import {
  Layers,
  Pencil,
  PlusCircle,
  Puzzle,
  Trash2,
} from "lucide-react"
import { toast } from "sonner"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { humaniseError } from "@/lib/api"
import { iconFor } from "@/lib/icons"
import {
  useConvBUs,
  useConvDataPoints,
  useConvIssueTypes,
  useConvTemplates,
  useCreateBU,
  useCreateIssueType,
  useCreateTemplate,
  useDeleteBU,
  useDeleteIssueType,
  useDeleteTemplate,
  useReplaceBindings,
  useUpdateBU,
  useUpdateIssueType,
  useUpdateTemplate,
} from "@/hooks/useConversationAdmin"
import type {
  ConvBusinessUnit,
  ConvDataPoint,
  ConvDataPointBinding,
  ConvIssueType,
} from "@/types"

// Kept in sync with app/conversation_studio/admin_routes.py::_MATRIX_INTENTS.
// If the backend adds one, add it here so admins can pick it.
const MATRIX_INTENTS = [
  "missing_item", "wrong_order", "cold_food",
  "never_arrived", "rider_late", "rider_rude", "rider_demanded_tip",
  "double_charge", "promo_failed",
  "cancel_request", "human_request", "vague", "other",
] as const

export function ConversationStudioPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Layers className="size-6 text-brand-600" />
          Conversation Studio
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure the chip-tap flow — business units, issue types, the
          data points each issue pulls, and the acknowledgment templates
          the customer sees.
        </p>
      </motion.div>

      <Tabs defaultValue="units">
        <TabsList>
          <TabsTrigger value="units">Business units</TabsTrigger>
          <TabsTrigger value="issues">Issue types</TabsTrigger>
          <TabsTrigger value="data">Data points</TabsTrigger>
        </TabsList>

        <TabsContent value="units" className="mt-4">
          <BusinessUnitsTab />
        </TabsContent>
        <TabsContent value="issues" className="mt-4">
          <IssueTypesTab />
        </TabsContent>
        <TabsContent value="data" className="mt-4">
          <DataPointsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ============================================================================
// Business Units
// ============================================================================

function BusinessUnitsTab() {
  const bus = useConvBUs()
  const createBU = useCreateBU()
  const updateBU = useUpdateBU()
  const deleteBU = useDeleteBU()

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ConvBusinessUnit | null>(null)

  if (bus.isLoading) return <TabLoading />

  return (
    <Card>
      <CardHeader row title={`Business units (${bus.data?.length ?? 0})`}>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <PlusCircle className="size-4" /> New unit
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Code</th>
              <th className="px-4 py-2">Sort</th>
              <th className="px-4 py-2">Active</th>
              <th className="w-24 px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {bus.data?.map((bu) => {
              const Icon = iconFor(bu.icon)
              return (
                <tr key={bu.id} className="border-t align-middle">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Icon className="size-4 text-muted-foreground" />
                      <span className="font-medium">{bu.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{bu.code}</td>
                  <td className="px-4 py-3">{bu.sort_order}</td>
                  <td className="px-4 py-3">
                    <Switch
                      checked={bu.is_active}
                      onCheckedChange={(v) =>
                        updateBU
                          .mutateAsync({ buId: bu.id, is_active: v })
                          .catch((e) => toast.error(humaniseError(e)))
                      }
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Edit"
                        onClick={() => setEditing(bu)}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Delete"
                        onClick={() =>
                          deleteBU
                            .mutateAsync(bu.id)
                            .then(() => toast.success("Unit deleted"))
                            .catch((e) => toast.error(humaniseError(e)))
                        }
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </CardContent>

      <BUFormDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={async (payload) => {
          await createBU.mutateAsync(payload)
        }}
      />
      <BUFormDialog
        open={!!editing}
        initial={editing ?? undefined}
        onClose={() => setEditing(null)}
        onSubmit={async (payload) => {
          if (!editing) return
          const { code: _code, ...rest } = payload
          await updateBU.mutateAsync({ buId: editing.id, ...rest })
        }}
      />
    </Card>
  )
}

function BUFormDialog({
  open,
  onClose,
  onSubmit,
  initial,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (payload: {
    code: string
    name: string
    icon: string | null
    sort_order: number
  }) => Promise<void>
  initial?: ConvBusinessUnit
}) {
  const [code, setCode] = useState(initial?.code ?? "")
  const [name, setName] = useState(initial?.name ?? "")
  const [icon, setIcon] = useState(initial?.icon ?? "Boxes")
  const [sortOrder, setSortOrder] = useState(initial?.sort_order ?? 100)

  const isEdit = !!initial
  const disabled = !code.trim() || !name.trim()

  const submit = async () => {
    try {
      await onSubmit({
        code: code.trim(),
        name: name.trim(),
        icon: icon.trim() || null,
        sort_order: sortOrder,
      })
      onClose()
    } catch (err) {
      toast.error(humaniseError(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit business unit" : "New business unit"}</DialogTitle>
          <DialogDescription>
            Business units group issue types in the customer chip tree.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="bu-code">Code</Label>
            <Input
              id="bu-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="orders"
              disabled={isEdit}
              maxLength={50}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bu-name">Name</Label>
            <Input
              id="bu-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Order issues"
              maxLength={100}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bu-icon">Icon (Lucide name)</Label>
            <Input
              id="bu-icon"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              placeholder="UtensilsCrossed"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bu-sort">Sort order</Label>
            <Input
              id="bu-sort"
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(Number(e.target.value) || 100)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={disabled}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Issue Types
// ============================================================================

function IssueTypesTab() {
  const bus = useConvBUs()
  const its = useConvIssueTypes()
  const dps = useConvDataPoints()
  const createIT = useCreateIssueType()
  const deleteIT = useDeleteIssueType()
  const updateIT = useUpdateIssueType()

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<ConvIssueType | null>(null)

  const busById = useMemo(() => {
    const m = new Map<string, ConvBusinessUnit>()
    bus.data?.forEach((b) => m.set(b.id, b))
    return m
  }, [bus.data])

  if (bus.isLoading || its.isLoading || dps.isLoading) return <TabLoading />

  return (
    <Card>
      <CardHeader row title={`Issue types (${its.data?.length ?? 0})`}>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <PlusCircle className="size-4" /> New issue type
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Business unit</th>
              <th className="px-4 py-2">Routes to intent</th>
              <th className="px-4 py-2">Data points</th>
              <th className="px-4 py-2">Active</th>
              <th className="w-24 px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {its.data?.map((it) => {
              const Icon = iconFor(it.icon)
              const bu = busById.get(it.business_unit_id)
              return (
                <tr key={it.id} className="border-t align-middle">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Icon className="size-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{it.name}</div>
                        <div className="text-xs text-muted-foreground font-mono">
                          {it.code}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">{bu?.name ?? "—"}</td>
                  <td className="px-4 py-3 text-xs font-mono">
                    {it.routes_to_intent ?? <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {it.data_points.length}
                  </td>
                  <td className="px-4 py-3">
                    <Switch
                      checked={it.is_active}
                      onCheckedChange={(v) =>
                        updateIT
                          .mutateAsync({ itId: it.id, is_active: v })
                          .catch((e) => toast.error(humaniseError(e)))
                      }
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Edit"
                        onClick={() => setEditing(it)}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Delete"
                        onClick={() =>
                          deleteIT
                            .mutateAsync(it.id)
                            .then(() => toast.success("Issue type deleted"))
                            .catch((e) => toast.error(humaniseError(e)))
                        }
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </CardContent>

      <IssueTypeFormDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        businessUnits={bus.data ?? []}
        onSubmit={async (payload) => {
          await createIT.mutateAsync(payload)
        }}
      />
      {editing && (
        <IssueTypeEditor
          issueType={editing}
          businessUnits={bus.data ?? []}
          dataPoints={dps.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  )
}

function IssueTypeFormDialog({
  open,
  onClose,
  onSubmit,
  businessUnits,
  initial,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (payload: {
    business_unit_id: string
    code: string
    name: string
    description: string | null
    icon: string | null
    routes_to_intent: string | null
    sort_order: number
  }) => Promise<void>
  businessUnits: ConvBusinessUnit[]
  initial?: ConvIssueType
}) {
  const [buId, setBuId] = useState(initial?.business_unit_id ?? "")
  const [code, setCode] = useState(initial?.code ?? "")
  const [name, setName] = useState(initial?.name ?? "")
  const [description, setDescription] = useState(initial?.description ?? "")
  const [icon, setIcon] = useState(initial?.icon ?? "HelpCircle")
  const [intent, setIntent] = useState(initial?.routes_to_intent ?? "")
  const [sortOrder, setSortOrder] = useState(initial?.sort_order ?? 100)

  const isEdit = !!initial
  const disabled = !buId || !code.trim() || !name.trim()

  const submit = async () => {
    try {
      await onSubmit({
        business_unit_id: buId,
        code: code.trim(),
        name: name.trim(),
        description: description.trim() || null,
        icon: icon.trim() || null,
        routes_to_intent: intent || null,
        sort_order: sortOrder,
      })
      onClose()
    } catch (err) {
      toast.error(humaniseError(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit issue type" : "New issue type"}</DialogTitle>
          <DialogDescription>
            Issue types are the leaf chips a customer taps. Binding them to a
            matrix intent lets Stage 2 apply the right refund/complaint policy.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="it-bu">Business unit</Label>
            <select
              id="it-bu"
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              value={buId}
              onChange={(e) => setBuId(e.target.value)}
            >
              <option value="" disabled>Select…</option>
              {businessUnits.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="it-code">Code</Label>
            <Input
              id="it-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="missing_item"
              disabled={isEdit}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="it-name">Name</Label>
            <Input
              id="it-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Missing item"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="it-icon">Icon (Lucide)</Label>
            <Input
              id="it-icon"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              placeholder="PackageX"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="it-intent">Routes to intent</Label>
            <select
              id="it-intent"
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
            >
              <option value="">— none —</option>
              {MATRIX_INTENTS.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="it-desc">Description</Label>
            <Textarea
              id="it-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="it-sort">Sort order</Label>
            <Input
              id="it-sort"
              type="number"
              value={sortOrder}
              onChange={(e) => setSortOrder(Number(e.target.value) || 100)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={disabled}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function IssueTypeEditor({
  issueType,
  businessUnits,
  dataPoints,
  onClose,
}: {
  issueType: ConvIssueType
  businessUnits: ConvBusinessUnit[]
  dataPoints: ConvDataPoint[]
  onClose: () => void
}) {
  const updateIT = useUpdateIssueType()
  const replaceBindings = useReplaceBindings()

  const templates = useConvTemplates(issueType.id)
  const createTpl = useCreateTemplate()
  const updateTpl = useUpdateTemplate()
  const deleteTpl = useDeleteTemplate()

  // Data point bindings the admin is editing. Snapshotted from server
  // state on open; saved via PUT on the button click.
  const [bindings, setBindings] = useState<ConvDataPointBinding[]>(
    issueType.data_points,
  )
  const boundIds = useMemo(
    () => new Set(bindings.map((b) => b.data_point_id)),
    [bindings],
  )

  const toggleBinding = (dp: ConvDataPoint) => {
    setBindings((prev) => {
      const existing = prev.find((b) => b.data_point_id === dp.id)
      if (existing) return prev.filter((b) => b.data_point_id !== dp.id)
      return [
        ...prev,
        {
          data_point_id: dp.id,
          is_required: true,
          sort_order: (prev[prev.length - 1]?.sort_order ?? 0) + 10,
        },
      ]
    })
  }

  const saveBindings = async () => {
    try {
      await replaceBindings.mutateAsync({
        itId: issueType.id,
        bindings,
      })
      toast.success("Data points saved")
    } catch (e) {
      toast.error(humaniseError(e))
    }
  }

  const [newTemplate, setNewTemplate] = useState("")

  return (
    <Dialog open onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{issueType.name}</DialogTitle>
          <DialogDescription>
            Configure this issue type's data-point contract and the pool
            of acknowledgment templates the customer will see.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-6">
          {/* --- Data points --- */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-semibold">Data points</div>
              <Button
                size="sm"
                variant="secondary"
                onClick={saveBindings}
                disabled={replaceBindings.isPending}
              >
                Save bindings
              </Button>
            </div>
            <div className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border p-2">
              {dataPoints.map((dp) => (
                <label
                  key={dp.id}
                  className="flex cursor-pointer items-start gap-2 rounded p-1.5 hover:bg-muted/50"
                >
                  <Checkbox
                    checked={boundIds.has(dp.id)}
                    onCheckedChange={() => toggleBinding(dp)}
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{dp.name}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {dp.description || dp.key}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* --- Templates --- */}
          <div>
            <div className="mb-2 text-sm font-semibold">
              Acknowledgment templates
            </div>
            {templates.isLoading && <TabLoading />}
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {templates.data?.map((tpl) => (
                <div
                  key={tpl.id}
                  className="rounded-md border bg-card p-2 text-sm"
                >
                  <Textarea
                    rows={2}
                    defaultValue={tpl.template}
                    onBlur={(e) => {
                      const next = e.target.value
                      if (next !== tpl.template) {
                        updateTpl
                          .mutateAsync({
                            tplId: tpl.id,
                            itId: issueType.id,
                            template: next,
                          })
                          .catch((err) => toast.error(humaniseError(err)))
                      }
                    }}
                    className="mb-1"
                  />
                  <div className="flex items-center justify-between text-xs">
                    <label className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">Weight</span>
                      <Input
                        type="number"
                        min={1}
                        max={100}
                        defaultValue={tpl.weight}
                        className="h-7 w-16"
                        onBlur={(e) => {
                          const w = Number(e.target.value)
                          if (w && w !== tpl.weight) {
                            updateTpl
                              .mutateAsync({
                                tplId: tpl.id,
                                itId: issueType.id,
                                weight: w,
                              })
                              .catch((err) => toast.error(humaniseError(err)))
                          }
                        }}
                      />
                    </label>
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1.5">
                        <span className="text-muted-foreground">Active</span>
                        <Switch
                          checked={tpl.is_active}
                          onCheckedChange={(v) =>
                            updateTpl
                              .mutateAsync({
                                tplId: tpl.id,
                                itId: issueType.id,
                                is_active: v,
                              })
                              .catch((err) => toast.error(humaniseError(err)))
                          }
                        />
                      </label>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Delete template"
                        onClick={() =>
                          deleteTpl
                            .mutateAsync({
                              tplId: tpl.id,
                              itId: issueType.id,
                            })
                            .catch((err) => toast.error(humaniseError(err)))
                        }
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              <div className="rounded-md border border-dashed p-2">
                <Textarea
                  rows={2}
                  placeholder="New template… {{customer.first_name}} etc."
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                />
                <div className="mt-1 flex justify-end">
                  <Button
                    size="sm"
                    disabled={!newTemplate.trim() || createTpl.isPending}
                    onClick={async () => {
                      try {
                        await createTpl.mutateAsync({
                          itId: issueType.id,
                          template: newTemplate.trim(),
                        })
                        setNewTemplate("")
                      } catch (err) {
                        toast.error(humaniseError(err))
                      }
                    }}
                  >
                    Add template
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Data Points (read-only registry)
// ============================================================================

function DataPointsTab() {
  const dps = useConvDataPoints()

  if (dps.isLoading) return <TabLoading />

  return (
    <Card>
      <CardHeader
        row
        title={`Data points (${dps.data?.length ?? 0})`}
        subtitle="Registry of Python fetchers. Read-only — new fetchers need a code deploy."
      >
        <Puzzle className="size-5 text-muted-foreground" />
      </CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Key</th>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Fetcher</th>
              <th className="px-4 py-2">Description</th>
            </tr>
          </thead>
          <tbody>
            {dps.data?.map((dp) => (
              <tr key={dp.id} className="border-t align-middle">
                <td className="px-4 py-3 font-mono text-xs">{dp.key}</td>
                <td className="px-4 py-3 font-medium">{dp.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {dp.fetcher_ref}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {dp.description}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

// ---------- helpers ----------

function TabLoading() {
  return (
    <div className="grid h-40 place-items-center">
      <LoaderCircleIcon
        size={24}
        animate
        animation="default"
        className="text-muted-foreground"
      />
    </div>
  )
}

/**
 * Local CardHeader wrapper — mimics shadcn's Card but with an inline
 * title/subtitle + arbitrary right-hand children slot. Keeps the tab
 * pages tidy without spawning another primitive.
 */
function CardHeader({
  title,
  subtitle,
  row = false,
  children,
}: {
  title: string
  subtitle?: string
  row?: boolean
  children?: React.ReactNode
}) {
  return (
    <div
      className={
        row
          ? "flex items-center justify-between border-b px-4 py-3"
          : "border-b px-4 py-3"
      }
    >
      <div>
        <div className="text-sm font-semibold">{title}</div>
        {subtitle && (
          <div className="text-xs text-muted-foreground">{subtitle}</div>
        )}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  )
}
