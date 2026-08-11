import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  ChatMessageResponse,
  SessionDetail,
  SessionSummary,
  Turn,
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

interface SendContext {
  previous: SessionDetail | undefined
}

export function useSendMessage() {
  const qc = useQueryClient()
  return useMutation<ChatMessageResponse, unknown, SendArgs, SendContext>({
    mutationFn: async ({ sessionId, message }) => {
      const { data } = await api.post<ChatMessageResponse>(
        `/api/sessions/${sessionId}/chat`,
        { message },
      )
      return data
    },
    // Optimistic update: append the user's message to the transcript
    // BEFORE the bot responds so the UI feels alive. If the request
    // fails we roll back (see onError). onSettled always refetches the
    // server truth so ordering + turn_no stay authoritative.
    onMutate: async ({ sessionId, message }) => {
      await qc.cancelQueries({ queryKey: sessionKeys.detail(sessionId) })
      const previous = qc.getQueryData<SessionDetail>(sessionKeys.detail(sessionId))

      if (previous) {
        const lastTurnNo = previous.turns.length
          ? previous.turns[previous.turns.length - 1].turn_no
          : 0
        const optimisticTurn: Turn = {
          turn_no: lastTurnNo + 1,
          role: "customer",
          message,
          actions: null,
          created_at: new Date().toISOString(),
        }
        qc.setQueryData<SessionDetail>(sessionKeys.detail(sessionId), {
          ...previous,
          turns: [...previous.turns, optimisticTurn],
        })
      }
      return { previous }
    },
    onError: (_err, { sessionId }, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(sessionKeys.detail(sessionId), ctx.previous)
      }
    },
    onSettled: (_res, _err, { sessionId }) => {
      qc.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) })
      qc.invalidateQueries({ queryKey: sessionKeys.list() })
    },
  })
}
