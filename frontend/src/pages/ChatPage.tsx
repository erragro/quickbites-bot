import { useEffect, useRef } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { toast } from "sonner"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { ShimmeringText } from "@/components/animate-ui/primitives/texts/shimmering"
import { ChipTree } from "@/components/ChipTree"
import { MessageBubble } from "@/components/MessageBubble"
import { MessageInput } from "@/components/MessageInput"
import { SessionSidebar } from "@/components/SessionSidebar"
import { humaniseError } from "@/lib/api"
import { useSelectIssue } from "@/hooks/useChatStarters"
import {
  useCreateSession,
  useSendMessage,
  useSessionDetail,
  useSessionList,
} from "@/hooks/useSessions"
import type { IssueTypeChip } from "@/types"

/**
 * Chat surface. Runs inside the AppShell (which owns the main app
 * sidebar), and adds its OWN inner sidebar for the session list.
 *
 * Two modes:
 *  - No sessionId in the URL → empty state; either shows a "start a new
 *    chat" prompt (if the user has no sessions yet) or auto-redirects to
 *    their most recent chat.
 *  - sessionId in the URL → fetches the transcript, renders turns, sends
 *    new messages through /api/sessions/{sid}/chat.
 */
export function ChatPage() {
  const nav = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()

  const list = useSessionList()
  const detail = useSessionDetail(sessionId)
  const send = useSendMessage()
  const createSession = useCreateSession()
  const selectIssue = useSelectIssue()

  // Chip-tap handler: if there's no session yet, mint one and land the
  // user on it; then trigger the select-issue call which persists the
  // bot ack turn server-side (the transcript invalidation in
  // useSelectIssue's onSuccess brings it into view).
  const handleChipSelect = async (
    issue: IssueTypeChip,
    businessUnitId: string,
  ) => {
    try {
      let sid = sessionId
      if (!sid) {
        const created = await createSession.mutateAsync({})
        sid = created.session_id
        nav(`/chat/${sid}`, { replace: true })
      }
      await selectIssue.mutateAsync({
        sessionId: sid,
        issue_type_id: issue.id,
      })
      // Silence the linter — businessUnitId isn't currently used
      // client-side but the API accepts it and future admin flows may
      // want to override BU choice explicitly. Keep the signature stable.
      void businessUnitId
    } catch (err) {
      toast.error(humaniseError(err, "Could not start this issue"))
    }
  }

  // Auto-redirect: if the URL has no session but the user has one already,
  // land them in the most recent chat.
  useEffect(() => {
    if (!sessionId && list.data && list.data.length > 0) {
      nav(`/chat/${list.data[0].session_id}`, { replace: true })
    }
  }, [sessionId, list.data, nav])

  // Auto-scroll to the newest message whenever the transcript grows.
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [detail.data?.turns.length, send.isPending])

  return (
    <div className="flex h-full w-full min-w-0">
      <SessionSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {renderBody()}
      </div>
    </div>
  )

  function renderBody() {
    // ----- Empty state: no session in URL -----
    if (!sessionId) {
      return (
        <ChipStarter
          onSelect={handleChipSelect}
          disabled={createSession.isPending || selectIssue.isPending}
          onFreeText={async (m) => {
            try {
              const created = await createSession.mutateAsync({})
              nav(`/chat/${created.session_id}`, { replace: true })
              await send.mutateAsync({ sessionId: created.session_id, message: m })
            } catch (err) {
              toast.error(humaniseError(err, "Could not start chat"))
            }
          }}
        />
      )
    }

    if (detail.isLoading) {
      return (
        <div className="grid h-full place-items-center">
          <LoaderCircleIcon
            size={28}
            animate
            animation="default"
            className="text-muted-foreground"
          />
        </div>
      )
    }

    if (detail.isError) {
      return (
        <div className="grid h-full place-items-center px-4 text-center">
          <div className="space-y-3">
            <p className="text-lg font-medium">Chat not found</p>
            <p className="text-sm text-muted-foreground">
              The chat you're looking for was deleted or doesn't belong to your account.
            </p>
          </div>
        </div>
      )
    }

    const turns = detail.data?.turns ?? []

    // Zero-turn session (session created but nothing sent yet) →
    // show the chip tree here too, not just on the URL-less empty state.
    // That way "start via chip" works whether the user came from the
    // sidebar's New button or from a fresh /chat visit.
    if (turns.length === 0) {
      return (
        <ChipStarter
          onSelect={handleChipSelect}
          disabled={selectIssue.isPending}
          onFreeText={async (message) => {
            try {
              await send.mutateAsync({ sessionId, message })
            } catch (err) {
              toast.error(humaniseError(err, "Message failed to send"))
            }
          }}
        />
      )
    }

    return (
      <div className="flex h-full flex-col">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto py-6">
          <AnimatePresence initial={false}>
            {turns.map((t) => (
              <MessageBubble
                key={`${t.turn_no}-${t.role}-${t.created_at}`}
                role={t.role}
                message={t.message ?? ""}
                actions={t.actions}
              />
            ))}
          </AnimatePresence>

          {send.isPending && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-start px-4"
            >
              <div className="rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-sm text-muted-foreground">
                <ShimmeringText text="Thinking…" />
              </div>
            </motion.div>
          )}
        </div>

        <MessageInput
          disabled={send.isPending}
          isSending={send.isPending}
          onSend={async (message) => {
            try {
              await send.mutateAsync({ sessionId, message })
            } catch (err) {
              toast.error(humaniseError(err, "Message failed to send"))
            }
          }}
        />
      </div>
    )
  }
}

/**
 * Empty-state surface: greeting + chip tree + free-text fallback.
 *
 * The chip tree scrolls (there can be more issue types than fit at
 * once), and the free-text input stays pinned at the bottom as the
 * "or type something" affordance for anything the taxonomy doesn't
 * cover.
 */
function ChipStarter({
  onSelect,
  onFreeText,
  disabled,
}: {
  onSelect: (issue: IssueTypeChip, businessUnitId: string) => void | Promise<void>
  onFreeText: (message: string) => void | Promise<void>
  disabled?: boolean
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-6 pt-8 text-center">
          <p className="text-2xl font-semibold tracking-tight">
            <ShimmeringText text="How can we help?" />
          </p>
          <p className="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
            Pick what happened and we'll take it from there — or type
            it out below.
          </p>
        </div>
        <ChipTree onSelect={onSelect} disabled={disabled} />
      </div>
      <MessageInput disabled={disabled} onSend={onFreeText} />
    </div>
  )
}
