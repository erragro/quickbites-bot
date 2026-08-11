import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { useAuthStore } from "@/stores/auth"
import type { AuthToken, User } from "@/types"

// -------------------------------------------------------------------------
// /auth/me — refetched on boot to hydrate the user object from the token.
// If the token is missing or expired, this fails, the request interceptor
// clears the store, and the AuthGuard sends us to /login.
// -------------------------------------------------------------------------

export function useMe() {
  const token = useAuthStore((s) => s.token)
  const setUser = useAuthStore((s) => s.setUser)
  const clearSession = useAuthStore((s) => s.clearSession)

  return useQuery({
    queryKey: ["auth", "me", token],
    queryFn: async (): Promise<User> => {
      try {
        const { data } = await api.get<User>("/auth/me")
        setUser(data)
        return data
      } catch (e) {
        clearSession()
        throw e
      }
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

// -------------------------------------------------------------------------
// /auth/login — email + password → token → store.
// -------------------------------------------------------------------------

interface LoginBody {
  email: string
  password: string
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession)
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (body: LoginBody): Promise<AuthToken> => {
      const { data } = await api.post<AuthToken>("/auth/login", body)
      return data
    },
    onSuccess: async (tokenResponse) => {
      // Store the token first so the follow-up /auth/me call is authenticated.
      useAuthStore.setState({ token: tokenResponse.access_token })
      const { data: user } = await api.get<User>("/auth/me")
      setSession(tokenResponse.access_token, user)
      // Invalidate everything session-related since we're now a new user.
      await qc.invalidateQueries({ queryKey: ["sessions"] })
    },
  })
}

// -------------------------------------------------------------------------
// /auth/signup — same shape as login, backend logs the user in immediately.
// -------------------------------------------------------------------------

export function useSignup() {
  const setSession = useAuthStore((s) => s.setSession)
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (body: LoginBody): Promise<AuthToken> => {
      const { data } = await api.post<AuthToken>("/auth/signup", body)
      return data
    },
    onSuccess: async (tokenResponse) => {
      useAuthStore.setState({ token: tokenResponse.access_token })
      const { data: user } = await api.get<User>("/auth/me")
      setSession(tokenResponse.access_token, user)
      await qc.invalidateQueries({ queryKey: ["sessions"] })
    },
  })
}

// -------------------------------------------------------------------------
// Log out — clear local state. No backend call needed for JWT (stateless).
// -------------------------------------------------------------------------

export function useLogout() {
  const clearSession = useAuthStore((s) => s.clearSession)
  const qc = useQueryClient()

  return () => {
    clearSession()
    qc.clear()
  }
}
