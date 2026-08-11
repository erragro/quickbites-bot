import { Outlet } from "react-router-dom"

import { GradientText } from "@/components/animate-ui/primitives/texts/gradient"
import { SessionSidebar } from "@/components/SessionSidebar"
import { UserMenu } from "@/components/UserMenu"

// Two-pane layout: sidebar (session list) on the left, current chat on the
// right. The header stays glued to the top of the right pane so the sidebar
// scrolls independently on long chat lists.
export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <SessionSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-5">
          <div className="text-lg font-semibold tracking-tight">
            <GradientText
              text="QuickBites Support"
              gradient="linear-gradient(90deg, #f97316 0%, #ec4899 50%, #6366f1 100%)"
            />
          </div>
          <UserMenu />
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
