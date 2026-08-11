import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { AuthGuard } from "@/components/AuthGuard"
import { ModuleGuard } from "@/components/ModuleGuard"
import { AdminPage } from "@/pages/AdminPage"
import { ChatPage } from "@/pages/ChatPage"
import { HomePage } from "@/pages/HomePage"
import { LoginPage } from "@/pages/LoginPage"
import { SignupPage } from "@/pages/SignupPage"

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },

  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          // Home — no module check, every authenticated user gets here.
          { index: true, element: <HomePage /> },

          // Chatbot — inside the /chat namespace, requires 'chatbot'
          // module access (any level).
          {
            path: "chat",
            element: <ModuleGuard moduleKey="chatbot" />,
            children: [
              { index: true, element: <ChatPage /> },
              { path: ":sessionId", element: <ChatPage /> },
            ],
          },

          // Admin — orthogonal to modules; gated by is_super_admin.
          {
            path: "admin",
            element: <ModuleGuard superAdminOnly />,
            children: [{ index: true, element: <AdminPage /> }],
          },
        ],
      },
    ],
  },

  { path: "*", element: <Navigate to="/" replace /> },
])
