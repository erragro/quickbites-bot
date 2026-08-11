import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

import type { User } from "@/types"

// Storage-key note: change this to invalidate all sessions on next deploy
// (e.g., after a breaking JWT change). Version bump = forced re-login for
// everyone. Cheap way to close the door on a leaked signing key.
const STORAGE_KEY = "quickbites-auth-v1"

interface AuthState {
  token: string | null
  user: User | null

  // Populated after a successful /auth/login or /auth/signup response
  setSession: (token: string, user: User) => void
  // Also called when /auth/me returns 401 (token expired) — clears local state
  clearSession: () => void
  // Called after a fresh /auth/me on page reload
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      clearSession: () => set({ token: null, user: null }),
      setUser: (user) => set({ user }),
    }),
    {
      name: STORAGE_KEY,
      // localStorage is XSS-exposed. For a portfolio project we accept this
      // trade-off (server-side httpOnly cookies would require CORS + CSRF
      // machinery that's out of scope). The Vervent-target readme calls
      // this limitation out explicitly.
      storage: createJSONStorage(() => localStorage),
      // Only persist the token; user is refetched from /auth/me on boot.
      partialize: (state) => ({ token: state.token }),
    },
  ),
)
