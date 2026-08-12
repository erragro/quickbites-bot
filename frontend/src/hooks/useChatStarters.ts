import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { sessionKeys } from "@/hooks/useSessions"
import type {
  ChatStartersResponse,
  SelectIssueRequest,
  SelectIssueResponse,
} from "@/types"

export const starterKeys = {
  all: ["chat-starters"] as const,
  tree: () => [...starterKeys.all, "tree"] as const,
}

/**
 * The chip tree the empty-chat state renders. Cached across page views —
 * it only changes when an admin edits the Conversation Studio config,
 * which is rare, so 5-minute staleTime is fine.
 */
export function useChatStarters() {
  return useQuery({
    queryKey: starterKeys.tree(),
    queryFn: async (): Promise<ChatStartersResponse> => {
      const { data } = await api.get<ChatStartersResponse>("/api/chat/starters")
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

interface SelectArgs extends SelectIssueRequest {
  sessionId: string
}

export function useSelectIssue() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ sessionId, ...body }: SelectArgs): Promise<SelectIssueResponse> => {
      const { data } = await api.post<SelectIssueResponse>(
        `/api/sessions/${sessionId}/select-issue`,
        body,
      )
      return data
    },
    onSuccess: (_res, { sessionId }) => {
      // The bot ack was persisted server-side — refetch to render it in
      // the transcript, and refresh the sidebar (title may have been
      // auto-set from the issue name).
      qc.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) })
      qc.invalidateQueries({ queryKey: sessionKeys.list() })
    },
  })
}
