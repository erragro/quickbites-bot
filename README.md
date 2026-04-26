# QuickBites Support Bot

A GenAI customer-support bot for the QuickBites food-delivery take-home.
Talks to the hosted simulator, decides refund / complaint / escalate /
flag-abuse / close actions per turn, auto-graded on a 22-scenario prod set.

**Live service:** https://quickbites-bot-162392320588.asia-south1.run.app
**Final graded score:** **1960 / 2200 = 89.1%** (14 perfect scenarios). See
[`docs/DESIGN.md`](docs/DESIGN.md) for architecture, per-scenario
post-mortem, and the 7 follow-on fixes shipped after the run.

Architecture: Cardinal-inspired **5-phase synchronous pipeline** (Validator
→ Deduplicator → Handler → Enricher → Dispatcher) followed by a **4-stage
LLM pipeline** (Classify → Evaluate → Validate → Respond), all inside a
single FastAPI handler.

## Quick start (against the live service)

No setup required — the service is deployed and accepts requests.

```bash
URL=https://quickbites-bot-162392320588.asia-south1.run.app

# liveness
curl -sf "$URL/ping"

# run a rehearsal scenario end-to-end against the simulator
curl -s -X POST "$URL/run/dev" \
     -H 'content-type: application/json' \
     -d '{"scenario_id": 101}' | jq .

# inspect a persisted session transcript with per-turn stage trace
curl -s "$URL/sessions/<session_id>" | jq .

# locked prod score (read-only — quota is consumed)
curl -s "$URL/score" | jq .
```

`POST /run/prod` will return `sessions_run: 0` against the live URL — the
simulator's 22-scenario prod quota was consumed during the original eval.
`/run/dev` (rehearsal scenarios 101–105) is still freely runnable.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/ping` | liveness (Cloud Run frontend reserves `/healthz`) |
| `POST` | `/run/dev` | run one rehearsal scenario (body: `{scenario_id?: 101-105}`) |
| `POST` | `/run/dev/all` | run all rehearsal scenarios 101-105 |
| `POST` | `/run/prod` | iterate prod sessions until simulator returns 409 |
| `GET`  | `/sessions` | list recent sessions |
| `GET`  | `/sessions/{id}` | full transcript + per-turn stage trace |
| `GET`  | `/score` | proxy to simulator `/v1/candidate/summary` |

## Testing the bot (Postman)

A demo-ready Postman collection ships at
[`postman/QuickBites.postman_collection.json`](postman/QuickBites.postman_collection.json),
and a step-by-step reviewer walkthrough lives in
[`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md).

**Quick version:** install Postman, import the collection, and run the
requests in order:

1. **Health & score** — confirm the service is up, see the locked
   `1960/2200 = 89.1%` from the prod simulator.
2. **Demo — good path** — Sc 101 (cold food, clean customer): refund +
   restaurant complaint via the matrix.
3. **Demo — adversarial** — Sc 104 (injection → pivot, abuser): silent
   refusal with abuse flag; Sc 103 (abuser soft claim): token credit +
   escalate + flag.
4. **Inspect** — drill into the persisted transcript for the most recent
   demo run; the collection auto-captures `sessionId` from each `/run/dev`
   response.

The collection ships with `baseUrl` already pointing at the Cloud Run
service. Flip it to `http://localhost:8000` to demo against the local
docker-compose stack instead. See
[`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md) for what to expect from
each response and how to read the override traces.

## Local development

For iteration on the policy / matrix / Stage 2 logic.

```bash
cp .env.example .env     # fill ANTHROPIC_API_KEY, SIMULATOR_BASE_URL, CANDIDATE_TOKEN
docker compose up --build
```

```bash
curl -X POST http://localhost:8000/run/dev \
     -H 'content-type: application/json' \
     -d '{"scenario_id": 101}' | jq .
```

Local stack uses Postgres in a separate container (via `docker-compose.yml`);
the Cloud Run image bundles Postgres into the same container (see
[`Dockerfile.cloudrun`](Dockerfile.cloudrun) and
[`cloudrun-entrypoint.sh`](cloudrun-entrypoint.sh)).

## Cloud Run deployment

Image is built by Cloud Build (avoids local-network registry pushes) and
deployed to `asia-south1` (same region as the simulator).

```bash
# rebuild + push to Artifact Registry
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_TAG=v2 \
  --project=project-2d37241a-3276-4c0d-b31 \
  --region=asia-south1

# redeploy
gcloud run deploy quickbites-bot \
  --image=asia-south1-docker.pkg.dev/project-2d37241a-3276-4c0d-b31/quickbites/bot:v2 \
  --region=asia-south1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 --memory=1Gi --cpu=1 \
  --no-cpu-throttling --max-instances=1 --timeout=3600
```

Required runtime env vars (set via `--set-env-vars` on `gcloud run deploy`):
`LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_FAST_MODEL`,
`ANTHROPIC_MODEL`, `SIMULATOR_BASE_URL`, `CANDIDATE_TOKEN`.

## Tests

```bash
.venv/bin/pytest
```

60 offline tests covering `abuse_rules`, `refund_matrix`, `stage2_validator`
hard rules, and `phase1_validator` injection detection. Tests run without
Postgres or any LLM credentials.

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
│   ├── phase1_validator.py     schema + injection scan
│   ├── phase2_deduplicator.py  in-proc SHA-256 cache, 10-min TTL
│   ├── phase3_handler.py       session state + history rehydrate
│   ├── phase4_enricher.py      Postgres pre-fetch
│   └── phase5_dispatcher.py    escalation_group + execution_id
├── l2_agents/                4-stage LLM pipeline
│   ├── stage0_classifier.py    Haiku: intent, order_id, sentiment, injection
│   ├── stage1_evaluator.py     Sonnet: structured action proposal
│   ├── stage2_validator.py     deterministic hard rules (no LLM)
│   ├── stage3_responder.py     Sonnet: prose + final actions JSON
│   ├── tools.py
│   └── llm_provider.py         Anthropic / Gemini Gateway abstraction
├── policies/
│   ├── policy_loader.py        caches policy_and_faq.md
│   ├── abuse_rules.py          pure functions
│   ├── refund_matrix.py        deterministic refund table
│   └── compensation_caps.py    tier-aware caps
└── runners/
    ├── session_runner.py       1 session end-to-end
    ├── dev_runner.py
    └── prod_runner.py
data/app.db                   bundled seed, migrated into Postgres on boot
policy_and_faq.md             bundled, loaded into Stage 1 system prompt
Dockerfile                    local dev (separate Postgres container)
Dockerfile.cloudrun           Cloud Run (bundled Postgres on tmpfs)
cloudbuild.yaml               Cloud Build pipeline
```

## Env vars

See [`.env.example`](.env.example). Required: `ANTHROPIC_API_KEY`,
`SIMULATOR_BASE_URL`, `CANDIDATE_TOKEN`. Optional tuning:
`refund_soft_cap_inr` (default 1500), `confidence_floor` (default 0.6),
`dedup_ttl_seconds` (default 600).
