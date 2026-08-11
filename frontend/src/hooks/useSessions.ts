import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  ChatMessageResponse,
  SessionDetail,
  SessionSummary,
} from "@/types"

// Central query-key factory so invalidations stay consistent across hooks.
export const sessionKeys = {
  all: ["sessions"] as const,
  list: () => [...sessionKeys.all, "list"] as const,
  detail: (sid: string) => [...sessionKeys.all, "detail", sid] as const,
}

export function useSessionList() {
  return useQuery({
    queryKey: sessionKeys.list(),
    queryFn: async (): Promise<SessionSummary[]> => {
      const { data } = await api.get<SessionSummary[]>("/api/sessions")
      return data
    },
  })
}

export function useSessionDetail(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionId ? sessionKeys.detail(sessionId) : ["session-detail-noop"],
    queryFn: async (): Promise<SessionDetail> => {
      const { data } = await api.get<SessionDetail>(`/api/sessions/${sessionId}`)
      return data
    },
    enabled: !!sessionId,
  })
}

interface CreateBody {
  title?: string | null
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CreateBody = {}): Promise<SessionSummary> => {
      const { data } = await api.post<SessionSummary>("/api/sessions", body)
      return data
    },
    onSuccess: (row) => {
      // Optimistic prepend so the sidebar shows the new chat immediately.
      qc.setQueryData<SessionSummary[]>(sessionKeys.list(), (prev) =>
        prev ? [row, ...prev] : [row],
      )
    },
  })
}

interface RenameArgs {
  sessionId: string
  title: string
}

export function useRenameSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ sessionId, title }: RenameArgs) => {
      const { data } = await api.patch<SessionSummary>(
        `/api/sessions/${sessionId}`,
        { title },
      )
      return data
    },
    onSuccess: (row) => {
      qc.setQueryData<SessionSummary[]>(sessionKeys.list(), (prev) =>
        prev?.map((s) => (s.session_id === row.session_id ? row : s)),
      )
      qc.invalidateQueries({ queryKey: sessionKeys.detail(row.session_id) })
    },
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionId: string) => {
      await api.delete(`/api/sessions/${sessionId}`)
      return sessionId
    },
    onSuccess: (sessionId) => {
      qc.setQueryData<SessionSummary[]>(sessionKeys.list(), (prev) =>
        prev?.filter((s) => s.session_id !== sessionId),
      )
      qc.removeQueries({ queryKey: sessionKeys.detail(sessionId) })
    },
  })
}

interface SendArgs {
  sessionId: string
  message: string
}

export function useSendMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ sessionId, message }: SendArgs): Promise<ChatMessageResponse> => {
      const { data } = await api.post<ChatMessageResponse>(
        `/api/sessions/${sessionId}/chat`,
        { message },
      )
      return data
    },
    onSuccess: (_res, { sessionId }) => {
      // Server-side is authoritative for the transcript; refetch to get
      // both the customer + bot turns with correct turn_no ordering.
      qc.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) })
      qc.invalidateQueries({ queryKey: sessionKeys.list() })
    },
  })
}
