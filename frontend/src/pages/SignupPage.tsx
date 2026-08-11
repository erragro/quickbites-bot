import { useState, type FormEvent } from "react"
import { Link, Navigate, useNavigate } from "react-router-dom"
import { motion } from "motion/react"

import { TypingText } from "@/components/animate-ui/primitives/texts/typing"
import { RippleButton } from "@/components/animate-ui/components/buttons/ripple"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { humaniseError } from "@/lib/api"
import { useSignup } from "@/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"

// Password rules mirror the backend Pydantic validator exactly (min 8, at
// least one letter + one digit). We show them inline as the user types so
// they don't hit the round-trip 422 for something we can prevent locally.
const MIN_PASSWORD_LEN = 8

function passwordProblems(v: string): string[] {
  const out: string[] = []
  if (v.length < MIN_PASSWORD_LEN) out.push(`at least ${MIN_PASSWORD_LEN} characters`)
  if (!/[A-Za-z]/.test(v)) out.push("one letter")
  if (!/\d/.test(v)) out.push("one digit")
  return out
}

export function SignupPage() {
  const nav = useNavigate()
  const token = useAuthStore((s) => s.token)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const signup = useSignup()

  if (token) return <Navigate to="/chat" replace />

  const problems = passwordProblems(password)
  const canSubmit =
    email.trim().length > 0 &&
    problems.length === 0 &&
    !signup.isPending

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await signup.mutateAsync({ email: email.trim(), password })
      nav("/chat")
    } catch (err) {
      setError(humaniseError(err, "Could not create account"))
    }
  }

  return (
    <div className="grid h-screen place-items-center bg-gradient-to-br from-brand-50 via-background to-background px-4 dark:from-brand-900/20">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32 }}
        className="w-full max-w-md"
      >
        <Card className="border-brand-200/40 shadow-xl backdrop-blur-sm">
          <CardHeader className="space-y-2 pb-4">
            <div className="text-2xl font-bold tracking-tight">
              <TypingText text="Create your account" duration={40} />
            </div>
            <p className="text-sm text-muted-foreground">
              Get started with QuickBites Support in a few seconds.
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={signup.isPending}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={signup.isPending}
                />
                {password.length > 0 && problems.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Still needed: {problems.join(", ")}.
                  </p>
                )}
              </div>
              {error && (
                <div
                  role="alert"
                  className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </div>
              )}
              <RippleButton
                type="submit"
                disabled={!canSubmit}
                className="w-full"
              >
                {signup.isPending ? "Creating account…" : "Create account"}
              </RippleButton>
              <p className="pt-2 text-center text-sm text-muted-foreground">
                Already have an account?{" "}
                <Link
                  to="/login"
                  className="font-medium text-brand-600 hover:underline"
                >
                  Sign in
                </Link>
              </p>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
