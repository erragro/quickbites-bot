import { useMemo, useState } from "react"
import { motion } from "motion/react"
import { CheckCircle2, PlusCircle, ShieldCheck, XCircle } from "lucide-react"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
            Grant and revoke module access, promote super-admins, and register new modules.
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
                <th className="px-4 py-2 font-medium">Modules</th>
                <th className="w-24 px-4 py-2 font-medium">Grant</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isSelf={u.id === currentUser?.id}
                  allModules={modules.data ?? []}
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

function UserRow({
  user,
  isSelf,
  allModules,
  modulesById,
}: {
  user: AdminUser
  isSelf: boolean
  allModules: ModuleInfo[]
  modulesById: Map<string, ModuleInfo>
}) {
  const update = useUpdateUser()
  const revoke = useRevokeAccess()

  const grantableModules = allModules.filter(
    (m) => !user.module_accesses.find((a) => a.module_id === m.id),
  )

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
        </div>
      </td>
      <td className="px-4 py-3">
        <button
          type="button"
          onClick={() => setActive(!user.is_active)}
          disabled={isSelf && user.is_active}
          className={cn(
            "inline-flex items-center gap-1 text-xs font-medium",
            user.is_active ? "text-emerald-600" : "text-muted-foreground",
            isSelf && user.is_active && "cursor-not-allowed opacity-70",
          )}
          title={isSelf && user.is_active ? "Cannot deactivate yourself" : undefined}
        >
          {user.is_active ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
          {user.is_active ? "Active" : "Disabled"}
        </button>
      </td>
      <td className="px-4 py-3">
        <button
          type="button"
          onClick={() => setSuperAdmin(!user.is_super_admin)}
          className={cn(
            "inline-flex items-center gap-1 text-xs font-medium",
            user.is_super_admin ? "text-brand-600" : "text-muted-foreground",
          )}
        >
          <ShieldCheck className="size-4" />
          {user.is_super_admin ? "Yes" : "No"}
        </button>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {user.module_accesses.length === 0 && (
            <span className="text-xs text-muted-foreground">No modules granted</span>
          )}
          {user.module_accesses.map((a) => {
            const module = modulesById.get(a.module_id)
            const Icon = iconFor(module?.icon)
            return (
              <span
                key={a.module_id}
                className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[11px]"
              >
                <Icon className="size-3" />
                <span>{a.module_name}</span>
                <span className="text-muted-foreground">·</span>
                <span className="uppercase tracking-widest">{a.access_level}</span>
                <button
                  type="button"
                  onClick={() =>
                    revoke
                      .mutateAsync({ userId: user.id, moduleId: a.module_id })
                      .catch((err) => toast.error(humaniseError(err)))
                  }
                  className="ml-1 text-muted-foreground hover:text-destructive"
                  aria-label={`Revoke ${a.module_name}`}
                >
                  ×
                </button>
              </span>
            )
          })}
        </div>
      </td>
      <td className="px-4 py-3">
        {grantableModules.length === 0 ? (
          <span className="text-[11px] text-muted-foreground">All granted</span>
        ) : (
          <GrantMenu user={user} grantableModules={grantableModules} />
        )}
      </td>
    </tr>
  )
}

function GrantMenu({
  user,
  grantableModules,
}: {
  user: AdminUser
  grantableModules: ModuleInfo[]
}) {
  const grant = useGrantAccess()
  const [selectedModule, setSelectedModule] = useState<ModuleInfo | null>(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium hover:bg-muted focus-visible:ring-2 focus-visible:ring-brand-400 outline-none">
          <PlusCircle className="size-3" />
          Grant
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          {grantableModules.map((m) => (
            <DropdownMenuItem
              key={m.id}
              onSelect={() => queueMicrotask(() => setSelectedModule(m))}
            >
              {m.name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={!!selectedModule} onOpenChange={(open) => !open && setSelectedModule(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Grant {selectedModule?.name}</DialogTitle>
            <DialogDescription>
              Select the access level for {user.email}.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            {ACCESS_LEVELS.map((lvl) => (
              <Button
                key={lvl}
                variant="secondary"
                disabled={grant.isPending}
                onClick={async () => {
                  if (!selectedModule) return
                  try {
                    await grant.mutateAsync({
                      userId: user.id,
                      moduleId: selectedModule.id,
                      accessLevel: lvl,
                    })
                    setSelectedModule(null)
                  } catch (err) {
                    toast.error(humaniseError(err))
                  }
                }}
              >
                {lvl}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
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
