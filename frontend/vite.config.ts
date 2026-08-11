import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// Vite 8 + React 19 + Tailwind v4 (via the official first-party plugin).
// Path alias `@/` → src/ so shadcn/ui + Animate UI generators drop files
// in the expected place without extra config.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Send API calls to the FastAPI backend running locally on 8000 so we
      // can develop the SPA against a real backend without CORS gymnastics.
      "/auth": "http://localhost:8000",
      "/api": "http://localhost:8000",
      "/ping": "http://localhost:8000",
      "/run": "http://localhost:8000",
    },
  },
})
