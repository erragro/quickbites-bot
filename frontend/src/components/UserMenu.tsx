import { LogOut, UserRound } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useLogout } from "@/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"

/**
 * Account menu. Base UI's DropdownMenuTrigger accepts children directly;
 * the earlier `render={<Button/>}` form was crashing because Base UI's
 * prop-forwarding to a shadcn Button (which already spreads its own
 * onClick) conflicted with the Menu.Trigger's internal handlers. Direct
 * children is the documented pattern and behaves cleanly.
 */
export function UserMenu() {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()

  const initials = user?.email ? user.email.slice(0, 2).toUpperCase() : "??"

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-full outline-none ring-offset-background transition focus-visible:ring-2 focus-visible:ring-brand-400"
        aria-label="Account menu"
      >
        <Avatar className="size-8 cursor-pointer transition-opacity hover:opacity-90">
          <AvatarFallback className="bg-brand-500 text-xs font-semibold text-white">
            {initials}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex items-center gap-2 py-2">
          <UserRound className="size-4" />
          <span className="min-w-0 truncate">{user?.email ?? "Signed in"}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => logout()}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
