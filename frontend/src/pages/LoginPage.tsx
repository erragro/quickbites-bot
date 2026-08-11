import { useState, type FormEvent } from "react"
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom"
import { motion } from "motion/react"

import { TypingText } from "@/components/animate-ui/primitives/texts/typing"
import { RippleButton } from "@/components/animate-ui/components/buttons/ripple"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { humaniseError } from "@/lib/api"
import { useLogin } from "@/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"

export function LoginPage() {
  const nav = useNavigate()
  const loc = useLocation()
  const token = useAuthStore((s) => s.token)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const login = useLogin()

  if (token) return <Navigate to="/chat" replace />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await login.mutateAsync({ email: email.trim(), password })
      const returnTo = (loc.state as { from?: string })?.from ?? "/chat"
      nav(returnTo)
    } catch (err) {
      setError(humaniseError(err, "Could not sign in"))
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
              <TypingText text="Welcome back" duration={40} />
            </div>
            <p className="text-sm text-muted-foreground">
              Sign in to continue to QuickBites Support.
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
                  disabled={login.isPending}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={login.isPending}
                />
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
                disabled={login.isPending}
                className="w-full"
              >
                {login.isPending ? "Signing in…" : "Sign in"}
              </RippleButton>
              <p className="pt-2 text-center text-sm text-muted-foreground">
                Don't have an account?{" "}
                <Link
                  to="/signup"
                  className="font-medium text-brand-600 hover:underline"
                >
                  Create one
                </Link>
              </p>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
