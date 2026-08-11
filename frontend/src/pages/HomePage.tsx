import { Link } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight, Lock, Puzzle, ShieldCheck } from "lucide-react"

import { GradientText } from "@/components/animate-ui/primitives/texts/gradient"
import { ShimmeringText } from "@/components/animate-ui/primitives/texts/shimmering"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useModules } from "@/hooks/useModules"
import { iconFor } from "@/lib/icons"
import { useAuthStore } from "@/stores/auth"

/**
 * Landing page for signed-in users. Explains what this platform is (a
 * login/access-control shell that gates modules) and shows tiles for the
 * modules the caller has access to.
 *
 * Non-technical framing: this is deliberately spare. The page is the
 * "why" of the whole platform — access control to modules for people who
 * should have them — and each accessible module gets a click-target
 * card. Modules the caller can't access are hidden entirely (the sidebar
 * already tells them what's available; the home dash doesn't lecture).
 */
export function HomePage() {
  const user = useAuthStore((s) => s.user)
  const { data: modules = [] } = useModules()
  const accessible = modules.filter((m) => m.access_level !== null)

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28 }}
        className="space-y-3"
      >
        <div className="text-3xl font-bold tracking-tight md:text-4xl">
          <GradientText
            text="Welcome to QuickBites"
            gradient="linear-gradient(90deg, #f97316 0%, #ec4899 50%, #6366f1 100%)"
          />
        </div>
        <p className="max-w-2xl text-muted-foreground">
          A shared login layer that provisions the right modules to the
          right people. Nothing more, nothing less — the platform doesn't
          try to be everything. Each module lives on its own; the shell
          only cares about identity and access.
        </p>
        {user?.is_super_admin && (
          <div className="text-xs text-muted-foreground">
            You're signed in as a super-admin. Use the{" "}
            <Link to="/admin" className="text-brand-600 hover:underline">
              Admin panel
            </Link>{" "}
            to grant modules to new teammates.
          </div>
        )}
      </motion.div>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SystemCard
          icon={<Lock className="size-5 text-brand-600" />}
          title="Identity"
          body="Email + password sign-in. JWT-scoped API access. Rate-limited login."
        />
        <SystemCard
          icon={<ShieldCheck className="size-5 text-brand-600" />}
          title="Access control"
          body="Per-user, per-module. Three access levels. Super-admin bootstraps on first signup."
        />
        <SystemCard
          icon={<Puzzle className="size-5 text-brand-600" />}
          title="Module registry"
          body="Register new features from the admin panel; they show up in every sidebar automatically."
        />
      </div>

      <div className="mt-12">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">
            <ShimmeringText text="Your modules" />
          </h2>
          {accessible.length === 0 && (
            <span className="text-xs text-muted-foreground">
              You don't have access to any modules yet. Ask your admin.
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {accessible.map((m) => {
            const Icon = iconFor(m.icon)
            return (
              <motion.div
                key={m.id}
                whileHover={{ y: -2 }}
                transition={{ duration: 0.18 }}
              >
                <Link to={m.path} className="block">
                  <Card className="h-full border transition-colors hover:border-brand-400/60 hover:shadow-md">
                    <CardHeader className="flex flex-row items-center gap-3">
                      <div className="grid size-10 place-items-center rounded-md bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-200">
                        <Icon className="size-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{m.name}</div>
                        <div className="text-xs text-muted-foreground">
                          Access: {m.access_level}
                        </div>
                      </div>
                      <ArrowRight className="size-4 text-muted-foreground" />
                    </CardHeader>
                    {m.description && (
                      <CardContent className="pt-0 text-sm text-muted-foreground">
                        {m.description}
                      </CardContent>
                    )}
                  </Card>
                </Link>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function SystemCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <Card className="border-muted/40">
      <CardHeader className="flex flex-row items-center gap-3">
        {icon}
        <div className="font-medium">{title}</div>
      </CardHeader>
      <CardContent className="pt-0 text-sm text-muted-foreground">{body}</CardContent>
    </Card>
  )
}
