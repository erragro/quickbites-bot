# QuickBites Support Bot

A GenAI-powered customer support bot for the QuickBites food-delivery take-home
(`/Users/apple/Documents/techjays/quickbites-candidate-starter`). Talks to the
hosted simulator, decides refund / complaint / escalate / flag-abuse / close
actions per turn, and is auto-graded on the 22-scenario prod eval set.

Architecture: Cardinal-inspired **5-phase synchronous pipeline** (Validator →
Deduplicator → Handler → Enricher → Dispatcher) followed by a **4-stage LLM
pipeline** (Classify → Evaluate → Validate → Respond), all inside a single
FastAPI handler. Design notes in [`docs/DESIGN.md`](docs/DESIGN.md).

## One-command local run

```bash
cp .env.example .env     # fill ANTHROPIC_API_KEY, SIMULATOR_BASE_URL, CANDIDATE_TOKEN
docker compose up --build
```

Then:

```bash
# run a dev rehearsal scenario
curl -X POST http://localhost:8000/run/dev -H 'content-type: application/json' \
    -d '{"scenario_id": 101}' | jq .

# run all prod graded scenarios (stops at 409)
curl -X POST http://localhost:8000/run/prod | jq .

# final score
curl http://localhost:8000/score | jq .
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/healthz` | liveness |
| `POST` | `/run/dev` | run one rehearsal scenario (body: `{scenario_id?: 101-105}`) |
| `POST` | `/run/dev/all` | run all rehearsal scenarios 101-105 |
| `POST` | `/run/prod` | iterate prod sessions until simulator returns 409 |
| `GET`  | `/sessions` | list recent sessions |
| `GET`  | `/sessions/{id}` | full transcript + per-turn stage trace |
| `GET`  | `/score` | proxy to simulator `/v1/candidate/summary` |

## Tests

```bash
.venv/bin/pytest
```

Offline tests (no Postgres, no Anthropic) cover `abuse_rules`, `stage2_validator`
hard rules, and `phase1_validator` prompt-injection detection.

## Layout

```
app/
├── main.py                   FastAPI
├── config.py                 env, DATA_TODAY=2026-04-13
├── schemas.py                Pydantic DTOs
├── db.py                     SQLAlchemy engine
├── repository.py             Postgres read layer (shared by Phase 4 + tools)
├── simulator_client.py       httpx wrapper for QuickBites simulator
├── migrations/bootstrap.py   sqlite3 → Postgres copy on startup
├── l1_cardinal/              Phase 1–5 orchestrator
│   ├── pipeline.py
│   ├── phase1_validator.py   schema + injection scan
│   ├── phase2_deduplicator.py in-proc SHA-256 cache, 10-min TTL
│   ├── phase3_handler.py     session state + history rehydrate
│   ├── phase4_enricher.py    Postgres pre-fetch of order/customer/rider/restaurant
│   └── phase5_dispatcher.py  escalation_group + execution_id
├── l2_agents/                4-stage LLM pipeline
│   ├── stage0_classifier.py  Haiku: intent, order_id, sentiment, injection
│   ├── stage1_evaluator.py   Sonnet + tool-use
│   ├── stage2_validator.py   deterministic hard rules (no LLM)
│   ├── stage3_responder.py   Sonnet: prose + final actions JSON
│   ├── tools.py              7 repository-backed tools
│   └── anthropic_client.py
├── policies/
│   ├── policy_loader.py      caches policy_and_faq.md
│   └── abuse_rules.py        pure functions
└── runners/
    ├── session_runner.py     1 session end-to-end
    ├── dev_runner.py
    └── prod_runner.py
data/app.db                   bundled seed, migrated into Postgres on boot
policy_and_faq.md             bundled, loaded into Stage 1 system prompt
```

## Env vars

See `.env.example`. Required: `ANTHROPIC_API_KEY`, `SIMULATOR_BASE_URL`,
`CANDIDATE_TOKEN`. Optional tuning: `refund_soft_cap_inr` (default 1500),
`confidence_floor` (default 0.6), `dedup_ttl_seconds` (default 600).

## Deploying on Railway

The repo includes `Dockerfile` and `railway.toml`. Provision a Postgres addon,
wire `DATABASE_URL`, set the three secrets above, deploy. `bootstrap.run()`
runs on startup and is idempotent — subsequent deploys skip the copy.
