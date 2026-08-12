import { NavLink } from "react-router-dom"
import { motion } from "motion/react"
import { Home as HomeIcon, Layers, ShieldCheck } from "lucide-react"

import { UserMenu } from "@/components/UserMenu"
import { useModules } from "@/hooks/useModules"
import { iconFor } from "@/lib/icons"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/stores/auth"

/**
 * Global left-hand navigation.
 *
 * Rows:
 *  1. Home (always visible)
 *  2. Every module the caller has any access_level on
 *  3. Admin panel (super_admin only)
 *  4. Signed-in user's menu (avatar + sign-out)
 *
 * Iconography is data-driven: the backend module row carries an `icon`
 * name string, `iconFor` maps it to a Lucide component. Unknown names
 * fall back to a neutral `Boxes` icon rather than crashing.
 */
export function MainSidebar() {
  const user = useAuthStore((s) => s.user)
  const { data: modules = [] } = useModules()

  const visibleModules = modules.filter((m) => m.access_level !== null)

  return (
    <aside className="flex h-full w-16 shrink-0 flex-col items-center border-r bg-sidebar py-3 text-sidebar-foreground md:w-56 md:items-stretch md:px-2">
      <div className="hidden px-2 pb-3 md:block">
        <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          QuickBites
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        <NavItem to="/" label="Home" icon={<HomeIcon className="size-4" />} end />

        {visibleModules.length > 0 && (
          <div className="mt-2 hidden px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground md:block">
            Modules
          </div>
        )}
        {visibleModules.map((m) => {
          const Icon = iconFor(m.icon)
          return (
            <NavItem
              key={m.id}
              to={m.path}
              label={m.name}
              icon={<Icon className="size-4" />}
            />
          )
        })}

        {user?.is_super_admin && (
          <>
            <div className="mt-2 hidden px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground md:block">
              System
            </div>
            <NavItem
              to="/admin"
              label="Admin"
              icon={<ShieldCheck className="size-4" />}
              end
            />
            <NavItem
              to="/admin/conversation"
              label="Conversation Studio"
              icon={<Layers className="size-4" />}
            />
          </>
        )}
      </nav>

      <div className="mt-auto flex items-center justify-center pt-3 md:justify-start md:px-2">
        <UserMenu />
      </div>
    </aside>
  )
}

function NavItem({
  to,
  label,
  icon,
  end,
}: {
  to: string
  label: string
  icon: React.ReactNode
  end?: boolean
}) {
  return (
    <NavLink to={to} end={end} className="block">
      {({ isActive }) => (
        <motion.div
          whileHover={{ x: 2 }}
          transition={{ duration: 0.15 }}
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition-colors",
            "justify-center md:justify-start",
            isActive
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
          )}
          aria-label={label}
        >
          <span aria-hidden>{icon}</span>
          <span className="hidden md:inline">{label}</span>
        </motion.div>
      )}
    </NavLink>
  )
}
