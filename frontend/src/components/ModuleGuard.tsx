import { Navigate, Outlet, useLocation } from "react-router-dom"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { useModules } from "@/hooks/useModules"
import { useAuthStore } from "@/stores/auth"

interface Props {
  moduleKey?: string
  // Required access level; access-rank must be >= required. Defaults to
  // "view" so most module routes just need any level of access.
  minLevel?: "view" | "edit" | "admin"
  // If true, only super_admins can enter (used for /admin).
  superAdminOnly?: boolean
}

const RANK: Record<string, number> = { view: 0, edit: 1, admin: 2 }

export function ModuleGuard({
  moduleKey,
  minLevel = "view",
  superAdminOnly = false,
}: Props) {
  const user = useAuthStore((s) => s.user)
  const { data: modules, isLoading } = useModules()
  const loc = useLocation()

  // super_admin path is orthogonal to the module registry; it's the
  // "system" section (admin panel) that no module row protects.
  if (superAdminOnly) {
    if (!user) return null
    if (!user.is_super_admin) {
      return <Navigate to="/" replace state={{ blockedFrom: loc.pathname }} />
    }
    return <Outlet />
  }

  if (isLoading) {
    return (
      <div className="grid h-full min-h-[50vh] place-items-center">
        <LoaderCircleIcon size={28} className="text-muted-foreground" animate animation="default" />
      </div>
    )
  }

  const module = modules?.find((m) => m.key === moduleKey)
  const level = module?.access_level

  if (!module) {
    // Module not registered — either config drift or a stale link. Home
    // is safe fallback.
    return <Navigate to="/" replace />
  }

  if (!level || RANK[level] < RANK[minLevel]) {
    return <Navigate to="/" replace state={{ blockedFrom: loc.pathname }} />
  }

  return <Outlet />
}
