import axios, { AxiosError } from "axios"

import { useAuthStore } from "@/stores/auth"

// One shared Axios instance. Vite proxies /auth, /api, /run, /ping to the
// FastAPI backend during dev (see vite.config.ts); in prod the same paths
// hit the same origin, so no baseURL is needed.
export const api = axios.create({
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
})

// Attach the JWT to every request from the store. Reads directly from the
// store (not from a closure) so token rotations after login are picked up.
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`)
  }
  return config
})

// Any 401 back from the server clears the local session and lets the router
// redirect to /login. Prevents pages sitting on a stale token forever.
api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearSession()
    }
    return Promise.reject(error)
  },
)

// Best-effort humanise for FastAPI/Pydantic error bodies. Handles two shapes:
//   422 → { detail: [{msg, loc}] } — Pydantic validation
//   4xx → { detail: "single string" } — our own HTTPException uses
export function humaniseError(err: unknown, fallback = "Something went wrong"): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (err.message) return err.message
  }
  return fallback
}
