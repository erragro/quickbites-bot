import {
  AlertTriangle,
  Award,
  BadgePercent,
  BarChart3,
  Boxes,
  Clock,
  Cog,
  CreditCard,
  FileCog,
  FileText,
  FileWarning,
  HandCoins,
  HeartPulse,
  HelpCircle,
  Home,
  IdCard,
  IndianRupee,
  Landmark,
  Languages,
  LayoutDashboard,
  MessageSquare,
  MessageSquareMore,
  PackageMinus,
  PackageSearch,
  PackageX,
  Shield,
  ShieldCheck,
  ShieldPlus,
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
  // Sreshtha modules
  FileText,       // Contract Reader
  Shield,
  Award,          // Schemes Finder
  FileWarning,    // Complaint Helper
  Languages,      // future language picker
  // Rights Guide fact-card icons
  IndianRupee,    // minimum wage / earnings
  HeartPulse,     // injury / health
  AlertTriangle,  // escalation / grievance
  IdCard,         // e-Shram
  ShieldPlus,     // insurance schemes
  Landmark,       // state welfare boards
  // business units + issue types (Conversation Studio seeds — legacy)
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
