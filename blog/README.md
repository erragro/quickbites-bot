# Sreshtha blog

Static Vite + Tailwind v4 site. Uses the same brand tokens as the
Sreshtha app (indigo scale, marigold accent, Geist Variable font).

## Local

```bash
cd blog
npm install
npm run dev            # http://localhost:5173
```

## Deploy to Vercel

```bash
npm i -g vercel        # once
cd blog
vercel                 # first run: gives you a preview URL
vercel --prod          # ship
```

Vercel autodetects Vite. Build command: `npm run build`. Output: `dist/`.

## Files

- `index.html`: the blog post
- `src/main.css`: Tailwind v4 + Sreshtha brand tokens
- `public/favicon.svg`: favicon (mirrored from the app)
- `public/screenshots/`: product + sample contract images
- `package.json`, `vite.config.ts`: build pipeline

## To swap

- **Repo URL**: search `github.com/surajitchaudhuri/sreshtha` in
  `index.html` and replace with the actual path once pushed.
- **Byline**: search `Surajit Chaudhuri`.
- **Statute versions or state ordinance dates**: search the reference
  list at the bottom of `index.html`.
