import { Outlet } from "react-router-dom"

import { MainSidebar } from "@/components/MainSidebar"

/**
 * Outer shell for every authenticated route. Contains just the global
 * sidebar; each page controls its own header + inner layout so the chat
 * surface (with its session sub-sidebar) doesn't need to fight this
 * shell for space.
 */
export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <MainSidebar />
      <main className="flex min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
