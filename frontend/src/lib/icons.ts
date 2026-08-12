import {
  BadgePercent,
  BarChart3,
  Boxes,
  Clock,
  Cog,
  CreditCard,
  FileCog,
  HandCoins,
  HelpCircle,
  Home,
  LayoutDashboard,
  MessageSquare,
  MessageSquareMore,
  PackageMinus,
  PackageSearch,
  PackageX,
  ShieldCheck,
  Snowflake,
  Truck,
  UserRound,
  Users,
  UserX,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react"

// Central registry of Lucide icons the backend may reference by name.
// Modules (via /api/admin/modules) and issue types / business units
// (seeded into the Conversation Studio schema) both look up their icon
// here. Missing icons fall back to `Boxes` so a bad key never crashes
// the render — only shows a placeholder.
export const ICON_REGISTRY: Record<string, LucideIcon> = {
  // module registry
  Home,
  LayoutDashboard,
  MessageSquare,
  BarChart3,
  ShieldCheck,
  Users,
  Boxes,
  Cog,
  FileCog,
  // business units + issue types (Conversation Studio seeds)
  UtensilsCrossed,
  Truck,
  CreditCard,
  HelpCircle,
  PackageX,
  PackageSearch,
  PackageMinus,
  Snowflake,
  Clock,
  UserX,
  HandCoins,
  BadgePercent,
  UserRound,
  MessageSquareMore,
}

export function iconFor(name: string | null | undefined): LucideIcon {
  if (!name) return Boxes
  return ICON_REGISTRY[name] ?? Boxes
}
