import { defineConfig } from "vite"
import tailwindcss from "@tailwindcss/vite"

// Zero framework: Vite treats index.html as the entry, Tailwind v4 handles
// the CSS pipeline (matches the Sreshtha app's setup verbatim). Vercel
// autodetects Vite and runs `npm run build`, deploying `dist/`.
export default defineConfig({
  plugins: [tailwindcss()],
})
