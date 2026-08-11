import { useState, type KeyboardEvent } from "react"
import { SendHorizonal } from "lucide-react"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface Props {
  onSend: (message: string) => Promise<void> | void
  disabled?: boolean
  isSending?: boolean
}

export function MessageInput({ onSend, disabled, isSending }: Props) {
  const [value, setValue] = useState("")

  const send = async () => {
    const msg = value.trim()
    if (!msg || disabled || isSending) return
    setValue("")
    await onSend(msg)
  }

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline. Matches the ChatGPT muscle
    // memory 90% of users show up with.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="border-t bg-background px-4 py-3">
      <div
        className={cn(
          "flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-xs transition-shadow",
          "focus-within:border-brand-400 focus-within:shadow-md",
        )}
      >
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Type your message… (Shift+Enter for a new line)"
          rows={1}
          maxLength={4000}
          disabled={disabled}
          className="min-h-0 resize-none border-0 bg-transparent p-2 text-sm shadow-none focus-visible:ring-0"
        />
        <Button
          type="button"
          size="icon"
          onClick={send}
          disabled={!value.trim() || disabled || isSending}
          className="mb-1 size-9 shrink-0"
        >
          {isSending ? (
            <LoaderCircleIcon size={16} animate animation="default" />
          ) : (
            <SendHorizonal className="size-4" />
          )}
        </Button>
      </div>
      <div className="mt-1.5 flex justify-end px-2 text-[10px] text-muted-foreground">
        {value.length}/4000
      </div>
    </div>
  )
}
