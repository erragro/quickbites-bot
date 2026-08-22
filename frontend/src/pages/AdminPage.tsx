import { useMemo, useState } from "react"
import { motion } from "motion/react"
import { PlusCircle, ShieldCheck } from "lucide-react"
import { toast } from "sonner"

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
  useAdminModules,
  useAdminUsers,
  useGrantAccess,
  useRegisterModule,
  useRevokeAccess,
  useUpdateUser,
} from "@/hooks/useAdmin"
import { humaniseError } from "@/lib/api"
import { iconFor } from "@/lib/icons"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/stores/auth"
import type { AccessLevel, AdminUser, ModuleInfo } from "@/types"

const ACCESS_LEVELS: AccessLevel[] = ["view", "edit", "admin"]

export function AdminPage() {
  const currentUser = useAuthStore((s) => s.user)
  const users = useAdminUsers()
  const modules = useAdminModules()

  const [registerOpen, setRegisterOpen] = useState(false)

  const modulesById = useMemo(() => {
    const map = new Map<string, ModuleInfo>()
    modules.data?.forEach((m) => map.set(m.id, m))
    return map
  }, [modules.data])

  if (users.isLoading || modules.isLoading) {
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
            <ShieldCheck className="size-6 text-brand-600" />
            Admin panel
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Toggle module access per user, promote super-admins, and register new modules.
          </p>
        </div>
        <Button onClick={() => setRegisterOpen(true)} className="gap-1.5">
          <PlusCircle className="size-4" />
          Register module
        </Button>
      </motion.div>

      <Card>
        <CardHeader className="border-b py-3 text-sm font-semibold">
          Users ({users.data?.length ?? 0})
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase tracking-widest text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Active</th>
                <th className="px-4 py-2 font-medium">Super-admin</th>
                {modules.data?.map((m) => (
                  <th key={m.id} className="px-4 py-2 font-medium">
                    <div className="flex items-center gap-1.5">
                      <Icon module={m} />
                      {m.name}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.data?.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isSelf={u.id === currentUser?.id}
                  modules={modules.data ?? []}
                  modulesById={modulesById}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <RegisterModuleDialog open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  )
}

function Icon({ module }: { module: ModuleInfo }) {
  const I = iconFor(module.icon)
  return <I className="size-3" />
}

/**
 * One row per user. Columns for active + super-admin toggles, then one
 * column per registered module with a Switch. Toggling the switch on
 * grants view access by default; a small dropdown appears next to the
 * switch to bump the level to edit or admin. Toggling off revokes.
 *
 * No dialogs, no chip-with-× pattern — everything is a direct toggle,
 * which the earlier "click a dropdown, pick a level, confirm a dialog"
 * flow was hiding behind three interactions.
 */
function UserRow({
  user,
  isSelf,
  modules,
  modulesById: _modulesById,
}: {
  user: AdminUser
  isSelf: boolean
  modules: ModuleInfo[]
  modulesById: Map<string, ModuleInfo>
}) {
  const update = useUpdateUser()

  const accessByModule = useMemo(() => {
    const m = new Map<string, AccessLevel>()
    user.module_accesses.forEach((a) => m.set(a.module_id, a.access_level))
    return m
  }, [user.module_accesses])

  const setActive = (next: boolean) =>
    update
      .mutateAsync({ userId: user.id, is_active: next })
      .catch((err) => toast.error(humaniseError(err)))

  const setSuperAdmin = (next: boolean) =>
    update
      .mutateAsync({ userId: user.id, is_super_admin: next })
      .catch((err) => toast.error(humaniseError(err)))

  return (
    <tr className="border-t align-middle">
      <td className="px-4 py-3">
        <div className="font-medium">{user.email}</div>
        <div className="text-xs text-muted-foreground">
          joined {new Date(user.created_at).toLocaleDateString()}
          {isSelf && <span className="ml-1.5 text-brand-600">· you</span>}
        </div>
      </td>
      <td className="px-4 py-3">
        <Switch
          checked={user.is_active}
          onCheckedChange={setActive}
          disabled={isSelf && user.is_active}
          aria-label={`Toggle active for ${user.email}`}
        />
      </td>
      <td className="px-4 py-3">
        <Switch
          checked={user.is_super_admin}
          onCheckedChange={setSuperAdmin}
          aria-label={`Toggle super-admin for ${user.email}`}
        />
      </td>
      {modules.map((m) => (
        <td key={m.id} className="px-4 py-3">
          <ModuleAccessCell
            user={user}
            module={m}
            currentLevel={accessByModule.get(m.id) ?? null}
          />
        </td>
      ))}
    </tr>
  )
}

/**
 * A Switch + level dropdown combined. Off → revoked. On → granted at
 * the level shown to the right (view/edit/admin). Flipping level
 * without turning off just changes the tier.
 */
function ModuleAccessCell({
  user,
  module,
  currentLevel,
}: {
  user: AdminUser
  module: ModuleInfo
  currentLevel: AccessLevel | null
}) {
  const grant = useGrantAccess()
  const revoke = useRevokeAccess()

  const enabled = currentLevel !== null
  const busy = grant.isPending || revoke.isPending

  const onToggle = async (next: boolean) => {
    try {
      if (next) {
        // Default new grants to view — most permissive level requires
        // a deliberate second interaction, not just "flip switch".
        await grant.mutateAsync({
          userId: user.id,
          moduleId: module.id,
          accessLevel: "view",
        })
      } else {
        await revoke.mutateAsync({ userId: user.id, moduleId: module.id })
      }
    } catch (err) {
      toast.error(humaniseError(err))
    }
  }

  const onChangeLevel = async (level: AccessLevel) => {
    if (level === currentLevel) return
    try {
      await grant.mutateAsync({
        userId: user.id,
        moduleId: module.id,
        accessLevel: level,
      })
    } catch (err) {
      toast.error(humaniseError(err))
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Switch
        checked={enabled}
        onCheckedChange={onToggle}
        disabled={busy}
        aria-label={`Toggle ${module.name} access for ${user.email}`}
      />
      {enabled && (
        <select
          value={currentLevel ?? "view"}
          onChange={(e) => onChangeLevel(e.target.value as AccessLevel)}
          disabled={busy}
          className={cn(
            "h-7 rounded-md border bg-background px-1.5 text-xs",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400",
          )}
          aria-label={`Access level for ${module.name}`}
        >
          {ACCESS_LEVELS.map((lvl) => (
            <option key={lvl} value={lvl}>
              {lvl}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

function RegisterModuleDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const register = useRegisterModule()
  const [key, setKey] = useState("")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [path, setPath] = useState("")
  const [icon, setIcon] = useState("Boxes")

  const reset = () => {
    setKey("")
    setName("")
    setDescription("")
    setPath("")
    setIcon("Boxes")
  }

  const handleSubmit = async () => {
    try {
      await register.mutateAsync({
        key: key.trim(),
        name: name.trim(),
        description: description.trim() || undefined,
        path: path.trim(),
        icon: icon.trim() || undefined,
      })
      reset()
      onClose()
      toast.success("Module registered")
    } catch (err) {
      toast.error(humaniseError(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register new module</DialogTitle>
          <DialogDescription>
            The module will show up in every user's sidebar once granted.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="mod-key">Key (lowercase, no spaces)</Label>
            <Input
              id="mod-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="analytics"
              maxLength={50}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mod-name">Display name</Label>
            <Input
              id="mod-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Analytics"
              maxLength={100}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mod-path">Frontend route</Label>
            <Input
              id="mod-path"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/analytics"
              maxLength={100}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mod-icon">Icon (Lucide name)</Label>
            <Input
              id="mod-icon"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              placeholder="BarChart3"
              maxLength={50}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mod-desc">Description</Label>
            <Textarea
              id="mod-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              maxLength={1000}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={register.isPending}>
            {register.isPending ? "Registering…" : "Register"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
