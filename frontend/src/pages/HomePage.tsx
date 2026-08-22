import { Link } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight, FileText, Languages, ShieldCheck } from "lucide-react"

import { GradientText } from "@/components/animate-ui/primitives/texts/gradient"
import { ShimmeringText } from "@/components/animate-ui/primitives/texts/shimmering"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useModules } from "@/hooks/useModules"
import { iconFor } from "@/lib/icons"
import { useAuthStore } from "@/stores/auth"

/**
 * Sreshtha landing for signed-in users.
 *
 * The frame: India has 7.7 crore gig workers, no product speaks their
 * language, and nobody translates the letter of the law into "here's
 * what to do this afternoon." Sreshtha is five modules that do exactly
 * that, on one shell.
 *
 * Hero carries a bilingual wordmark (English + Devanagari), a tagline
 * that names the audience, and three pillar cards. Module cards below
 * show whatever the caller has access to; inaccessible modules are
 * hidden (sidebar already lists them).
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
        className="space-y-4"
      >
        <div className="flex items-baseline gap-3">
          <div className="text-3xl font-bold tracking-tight md:text-4xl">
            <GradientText
              text="Sreshtha"
              gradient="linear-gradient(90deg, #4338ca 0%, #7c3aed 45%, #f59e0b 100%)"
            />
          </div>
          <div className="hidden text-2xl font-medium text-muted-foreground md:block">
            श्रेष्ठ
          </div>
        </div>
        <p className="max-w-2xl text-base text-foreground/80 md:text-lg">
          Rights, contracts, and support for India's gig workers.
          In <span className="font-medium text-brand-700 dark:text-brand-300">your language</span>.
        </p>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Upload the contract you signed and see it explained clause by clause.
          Ask about your rights and get answers you can cite. Find the government
          schemes you're already entitled to. Draft a complaint that actually
          goes somewhere.
        </p>
        {user?.is_super_admin && (
          <div className="pt-1 text-xs text-muted-foreground">
            You're signed in as a super-admin. Use the{" "}
            <Link to="/admin" className="text-brand-600 hover:underline">
              Admin panel
            </Link>{" "}
            to manage users and modules.
          </div>
        )}
      </motion.div>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <PillarCard
          icon={<Languages className="size-5 text-brand-600" />}
          title="Language-first"
          body="Hindi, Bengali, Tamil are first-class. English is a fallback, not the norm. Voice input on every field."
        />
        <PillarCard
          icon={<ShieldCheck className="size-5 text-brand-600" />}
          title="Rights, not advice"
          body="Every claim cites the statute or scheme. Deterministic decisions in code. AI handles language, never legal outcomes."
        />
        <PillarCard
          icon={<FileText className="size-5 text-brand-600" />}
          title="From reading to action"
          body="Read the contract, understand the clause, find the scheme, draft the complaint. One flow, one session."
        />
      </div>

      <div className="mt-12">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">
            <ShimmeringText text="Your tools" />
          </h2>
          {accessible.length === 0 && (
            <span className="text-xs text-muted-foreground">
              No tools enabled yet. Ask your admin to grant access.
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

      <div className="mt-16 border-t pt-6 text-xs text-muted-foreground">
        Sreshtha is information, not legal advice. For formal help, call
        India Labourline at <span className="font-medium">1800-419-1550</span>.
      </div>
    </div>
  )
}

function PillarCard({
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
