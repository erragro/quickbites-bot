import { motion } from "motion/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

interface Props {
  role: "customer" | "bot" | string
  message: string
  actions?: unknown
}

// Motion is deliberately gentle here — chat UIs feel wrong when message
// bubbles bounce in. The 240ms fade + tiny y-slide reads as "arriving"
// rather than "showing off".
const bubbleVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.24 } },
}

export function MessageBubble({ role, message, actions }: Props) {
  const isUser = role === "customer"

  return (
    <motion.div
      variants={bubbleVariants}
      initial="initial"
      animate="animate"
      className={cn(
        "flex w-full gap-2 px-4",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <Avatar className="mt-1 size-8 shrink-0 bg-brand-500 text-white">
          <AvatarFallback className="bg-brand-500 text-xs font-semibold text-white">
            QB
          </AvatarFallback>
        </Avatar>
      )}
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm",
        )}
      >
        <div className={cn("prose prose-sm max-w-none", isUser && "prose-invert")}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message}</ReactMarkdown>
        </div>
        {Array.isArray(actions) && actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {(actions as { type?: string }[]).map((a, i) => (
              <span
                key={i}
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  isUser
                    ? "bg-primary-foreground/20 text-primary-foreground"
                    : "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200",
                )}
              >
                {a.type ?? "action"}
              </span>
            ))}
          </div>
        )}
      </div>
      {isUser && (
        <Avatar className="mt-1 size-8 shrink-0">
          <AvatarFallback className="text-xs font-semibold">You</AvatarFallback>
        </Avatar>
      )}
    </motion.div>
  )
}
