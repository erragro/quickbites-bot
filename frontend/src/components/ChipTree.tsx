import { motion } from "motion/react"

import { LoaderCircleIcon } from "@/components/animate-ui/icons/loader-circle"
import { useChatStarters } from "@/hooks/useChatStarters"
import { iconFor } from "@/lib/icons"
import { cn } from "@/lib/utils"
import type { IssueTypeChip } from "@/types"

interface Props {
  onSelect: (issueType: IssueTypeChip, businessUnitId: string) => void | Promise<void>
  disabled?: boolean
}

/**
 * Chip-tap starter — the empty-chat state. Renders the BU tree flat:
 * business unit as a section header + a wrapping row of issue-type
 * pills underneath. Two levels of hierarchy visible at once, no
 * navigation needed — the tree is small (11 chips seeded) so a single
 * view beats screen-hopping for both speed and demoability.
 *
 * Tapping a chip fires `onSelect` and the parent handles session
 * bootstrapping + /api/sessions/{sid}/select-issue.
 */
export function ChipTree({ onSelect, disabled }: Props) {
  const { data, isLoading, isError } = useChatStarters()

  if (isLoading) {
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

  if (isError || !data) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Couldn't load the starter menu. Try refreshing.
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-6 py-8">
      {data.business_units.map((unit) => {
        const UnitIcon = iconFor(unit.icon)
        return (
          <motion.section
            key={unit.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22 }}
            className="space-y-3"
          >
            <div className="flex items-center gap-2">
              <div className="grid size-8 place-items-center rounded-md bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-200">
                <UnitIcon className="size-4" />
              </div>
              <h3 className="text-sm font-semibold tracking-tight">{unit.name}</h3>
            </div>
            <div className="flex flex-wrap gap-2 pl-10">
              {unit.issue_types.map((it) => (
                <ChipButton
                  key={it.id}
                  issue={it}
                  disabled={disabled}
                  onClick={() => onSelect(it, unit.id)}
                />
              ))}
            </div>
          </motion.section>
        )
      })}
    </div>
  )
}

function ChipButton({
  issue,
  disabled,
  onClick,
}: {
  issue: IssueTypeChip
  disabled?: boolean
  onClick: () => void
}) {
  const Icon = iconFor(issue.icon)
  return (
    <motion.button
      type="button"
      whileHover={{ y: -1 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.12 }}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "group inline-flex items-center gap-2 rounded-full border bg-card px-3.5 py-2 text-sm font-medium",
        "shadow-xs transition-colors hover:border-brand-400 hover:bg-brand-50 hover:text-brand-900",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "dark:hover:bg-brand-900/30 dark:hover:text-brand-100",
      )}
      title={issue.description ?? undefined}
    >
      <Icon className="size-4 text-muted-foreground group-hover:text-brand-700 dark:group-hover:text-brand-200" />
      <span>{issue.name}</span>
    </motion.button>
  )
}
