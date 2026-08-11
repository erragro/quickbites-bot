import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { MessageSquarePlus, MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
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
import { humaniseError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  useCreateSession,
  useDeleteSession,
  useRenameSession,
  useSessionList,
} from "@/hooks/useSessions"
import type { SessionSummary } from "@/types"

export function SessionSidebar() {
  const nav = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  const { data: sessions = [], isLoading } = useSessionList()
  const createSession = useCreateSession()

  const handleNewChat = async () => {
    try {
      const created = await createSession.mutateAsync({})
      nav(`/chat/${created.session_id}`)
    } catch (err) {
      toast.error(humaniseError(err, "Could not start a new chat"))
    }
  }

  return (
    <div className="flex h-full w-72 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="text-sm font-semibold tracking-tight">Chats</div>
        <Button
          size="sm"
          variant="secondary"
          onClick={handleNewChat}
          disabled={createSession.isPending}
          className="gap-1.5"
        >
          <MessageSquarePlus className="size-4" />
          New
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && (
          <div className="px-3 py-4 text-xs text-muted-foreground">
            Loading chats…
          </div>
        )}
        {!isLoading && sessions.length === 0 && (
          <div className="px-3 py-6 text-xs text-muted-foreground">
            No chats yet. Click <span className="font-medium">New</span> to start
            one.
          </div>
        )}

        <AnimatePresence initial={false} mode="popLayout">
          {sessions.map((s) => (
            <motion.div
              key={s.session_id}
              layout
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              <SidebarRow
                session={s}
                isActive={s.session_id === sessionId}
              />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function SidebarRow({
  session,
  isActive,
}: {
  session: SessionSummary
  isActive: boolean
}) {
  const nav = useNavigate()
  const rename = useRenameSession()
  const remove = useDeleteSession()

  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [draftTitle, setDraftTitle] = useState(session.title ?? "")

  const displayTitle = session.title?.trim() || "Untitled chat"

  const handleRename = async () => {
    if (!draftTitle.trim()) return
    try {
      await rename.mutateAsync({
        sessionId: session.session_id,
        title: draftTitle.trim(),
      })
      setRenameOpen(false)
    } catch (err) {
      toast.error(humaniseError(err, "Rename failed"))
    }
  }

  const handleDelete = async () => {
    try {
      await remove.mutateAsync(session.session_id)
      setDeleteOpen(false)
      if (isActive) nav("/chat")
    } catch (err) {
      toast.error(humaniseError(err, "Delete failed"))
    }
  }

  return (
    <>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm transition-colors",
          isActive
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "hover:bg-sidebar-accent/60",
        )}
      >
        <Link
          to={`/chat/${session.session_id}`}
          className="min-w-0 flex-1 truncate"
        >
          {displayTitle}
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="size-7 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100"
                aria-label="Chat options"
              >
                <MoreHorizontal className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault()
                setDraftTitle(session.title ?? "")
                setRenameOpen(true)
              }}
            >
              <Pencil className="size-4" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault()
                setDeleteOpen(true)
              }}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="size-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename chat</DialogTitle>
            <DialogDescription>
              Give this conversation a title that will help you find it later.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            maxLength={200}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                handleRename()
              }
            }}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRenameOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRename} disabled={rename.isPending}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this chat?</DialogTitle>
            <DialogDescription>
              The transcript will be permanently removed. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={remove.isPending}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
