import {
  BarChart3,
  Boxes,
  Cog,
  FileCog,
  Home,
  LayoutDashboard,
  MessageSquare,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react"

// Central registry of Lucide icons the backend module registry may
// reference by name. Every module registered through /api/admin/modules
// sets `icon: "MessageSquare"` (or any key in this map) and the frontend
// looks it up here. Missing icons fall back to `Boxes`.
export const ICON_REGISTRY: Record<string, LucideIcon> = {
  Home,
  LayoutDashboard,
  MessageSquare,
  BarChart3,
  ShieldCheck,
  Users,
  Boxes,
  Cog,
  FileCog,
}

export function iconFor(name: string | null | undefined): LucideIcon {
  if (!name) return Boxes
  return ICON_REGISTRY[name] ?? Boxes
}
