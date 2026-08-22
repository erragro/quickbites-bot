# Sreshtha

**An app for India's gig workers.**

Contract explanations, rights guidance, and complaint drafting, in the
languages workers actually speak. Powered by Google Gemini for
reasoning, Sarvam Mayura for translation, on an in-house Indic vision
stack.

Blog: (Vercel URL, update once deployed)

License: [MIT](LICENSE), © Surajit Chaudhuri.

---

## What's here

Two surfaces in this repo:

- `app/`: FastAPI backend. Auth, module registry, admin panel,
  Contract Reader pipeline (upload, EasyOCR, Gemini stages 1-3, Mayura
  translation with chunking + idiom substitution).
- `frontend/`: React 19 + Vite + Tailwind v4 + shadcn/ui client.
  Contract Reader UI, admin panels, sidebar shell for the four
  upcoming modules.

The Meet the Builders submission blog lives in a separate repo,
`sreshtha-blog`, and deploys to GitHub Pages.

## Modules

| Module            | Status |
|-------------------|--------|
| Contract Reader   | Live   |
| Rights Guide      | Next   |
| Chatbot Sahaayak  | Next   |
| Schemes Finder    | Next   |
| Complaint Helper  | Next   |

## Runtime

**Backend.** Python 3.13, FastAPI, SQLAlchemy 2, Postgres 16, Alembic
migrations. `pip install -e ".[dev]"`, then `uvicorn app.main:app`.

**Frontend.** Node 20, Vite 8, Tailwind v4. `cd frontend && npm run dev`.

**Database.** `docker compose up postgres` for local Postgres, then
`alembic upgrade head` to apply migrations.

**Env.** Copy `.env.example` to `.env`, fill in `GEMINI_API_KEY` or
`GOOGLE_APPLICATION_CREDENTIALS`, `SARVAM_API_KEY`, and `JWT_SECRET`.

## Testing

```bash
pytest                       # backend suite
cd frontend && npm run lint  # frontend lint
```

## Translation pipeline in one paragraph

Gemini 2.5 Flash runs three deterministic analysis stages (extract
clauses, annotate with statute + risk, rewrite for the worker), always
in English. Sarvam Mayura v1 translates the finished English into the
worker's chosen target language, with four register modes exposed on
the upload form. An Aho-Corasick idiom library (25 seeded phrases,
admin-extensible) scans every payload before Mayura sees it and swaps
matches for opaque tokens, then splices in pre-verified target-language
equivalents after translation returns. All translation calls chunk
multiple clauses per request to stay under Mayura's per-call cap and
Sarvam's rate limits.

## Docs

- [`docs/PRD.md`](docs/PRD.md): product requirements
- [`docs/DESIGN.md`](docs/DESIGN.md): architecture notes

## Contributing

Sreshtha is early. Partnership inquiries (unions, welfare boards,
platforms addressing Fairwork ratings): open an issue with the
`partnership` label.
