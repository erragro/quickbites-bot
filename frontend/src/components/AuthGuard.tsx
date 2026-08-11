import { Navigate, Outlet } from "react-router-dom"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { useMe } from "@/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"

/**
 * Wraps routes that require an authenticated user. If we hold a token but
 * haven't hydrated the user yet, show a loader while /auth/me resolves.
 * If the token is missing (or /auth/me 401's and clears the store), redirect
 * to /login and pass the current path in state so the login page can bounce
 * the user back after signing in.
 */
export function AuthGuard() {
  const token = useAuthStore((s) => s.token)
  const me = useMe()

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (me.isPending) {
    return (
      <div className="grid h-full min-h-[70vh] place-items-center">
        <LoaderCircleIcon
          size={32}
          className="text-muted-foreground"
          animate
          animation="default"
        />
      </div>
    )
  }

  if (me.isError) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
