import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { AuthGuard } from "@/components/AuthGuard"
import { ChatPage } from "@/pages/ChatPage"
import { LoginPage } from "@/pages/LoginPage"
import { SignupPage } from "@/pages/SignupPage"

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/signup",
    element: <SignupPage />,
  },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/chat", element: <ChatPage /> },
          { path: "/chat/:sessionId", element: <ChatPage /> },
        ],
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/chat" replace />,
  },
])
