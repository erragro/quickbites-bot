# QuickBites Support Bot — Design

## 0. Deployment

- **Live service:** https://quickbites-bot-162392320588.asia-south1.run.app
  (Cloud Run, region `asia-south1`, single instance, bundled Postgres on
  tmpfs, ~10s cold start, max 1 instance, 60-min request timeout).
- **Source:** https://github.com/erragro/quickbites-bot
- **Endpoints:** `GET /ping`, `POST /run/dev` (rehearsal 101–105),
  `POST /run/prod`, `GET /sessions/{id}`, `GET /score`.

## 1. Architecture

### Why a synchronous handler

The simulator blocks on `POST /reply` — it expects the bot to return the
next message and action list inline. Building this on Celery + a queue
would add latency, infrastructure, and one moving part for every turn,
without changing the protocol's blocking shape. So one FastAPI handler
runs everything per turn:

```
                            ┌─────────────────────────┐
        ───── customer ────▶│ FastAPI /reply (sync)   │
        simulator           │ blocks until reply ready│
                            └────────────┬────────────┘
                                         │
   ╔══════════════════════════════════════════════════════════════╗
   ║                  Cardinal pipeline (Python)                  ║
   ║──────────────────────────────────────────────────────────────║
   ║  Phase 1 │ Validator    │ shape, injection markers, abuse    ║
   ║  Phase 2 │ Deduplicator │ SHA-256(session+msg), 10m TTL      ║
   ║          │              │ • hit  → replay, persist, return   ║
   ║          │              │ • miss → continue                  ║
   ║  Phase 3 │ Handler      │ load/create session row + history  ║
   ║  Phase 4 │ Enricher     │ Postgres pre-fetch:                ║
   ║          │              │   order+items, customer+abuse,     ║
   ║          │              │   rider+history, restaurant+reviews║
   ║  Phase 5 │ Dispatcher   │ escalation_group + execution_id    ║
   ╠══════════════════════════════════════════════════════════════╣
   ║                LLM pipeline (provider-agnostic)              ║
   ║──────────────────────────────────────────────────────────────║
   ║  Stage 0 │ Classify   │ FAST  │ JSON: intent, mentioned_id,  ║
   ║          │            │       │   sentiment, injection?      ║
   ║  Stage 1 │ Evaluate   │ SMART │ structured: proposed actions ║
   ║          │            │       │   + reasoning + confidence   ║
   ║  Stage 2 │ Validate   │ NONE  │ deterministic enforcement    ║
   ║          │            │       │   (matrix + 14 hard rules)   ║
   ║  Stage 3 │ Respond    │ SMART │ JSON: bot_message            ║
   ╚══════════════════════════════════════════════════════════════╝
                                         │
                                         ▼
   simulator ◀──── POST /reply (bot_message + actions[]) ─────────
```

Each row in the diagram is one function call inside the handler — no
queue, no worker, no async. The two-pipeline split is the load-bearing
design choice: **everything that can be deterministic is**, the LLM only
runs where natural-language judgment is unavoidable, and **Stage 2 owns
the grading-relevant decisions** in plain Python.

### Why the deterministic Stage 2

The grader scores on six criteria — refund amount, refund cap, complaint
target, abuse handling, escalation correctness, clean close. Five of those
six are about *which actions get emitted*, which is a decision the LLM
shouldn't be allowed to make alone:

- LLMs drift on numbers turn-to-turn (cold-food at 30% one turn, 50% the
  next when the customer pushes back).
- LLMs cave to social pressure ("just process the refund NOW") on
  scenarios where the right answer is to refuse.
- LLMs are unreliable about emitting paired actions (refund + complaint)
  when the prompt only emphasises one.

So Stage 1 *proposes*, Stage 2 *enforces*: the matrix decides amounts and
partner complaints, abuse rules decide who gets refused, escalation rules
decide who gets routed to a human. Stage 1's contribution is intent
inference, reasoning trace, and a confidence score. Stage 2 is a few
hundred lines of Python with 60 unit tests.

### Why provider-agnostic

`app/l2_agents/llm_provider.py` exposes one `chat(role, system, user, …)`
contract where `role ∈ {"fast", "smart"}`. Two implementations ship:

- **AnthropicProvider** — `claude-haiku-4-5` (fast), `claude-sonnet-4-6`
  (smart). Default in production.
- **GeminiGatewayProvider** — `gemini-2.5-flash-lite` (fast),
  `gemini-2.5-flash` (smart). Used during early iteration on free quota.

Switching is one env var. Stages 0–3 don't know which model they're
talking to.

## 2. Data

`app.db` (the bundled SQLite seed) is loaded into Postgres at startup by
`app/migrations/bootstrap.py` (idempotent — skips if rows exist). Schema
is a straight copy of the 9 starter tables plus three runtime tables we
own: `sessions`, `turns`, `bot_executions`. `DATA_TODAY = 2026-04-13` is
pinned globally per the simulator's `schema.md`; every "last 30 days"
calculation uses it, so the bot's view of the world matches the snapshot
the simulator was built against.

In the Cloud Run image Postgres runs in the same container with `PGDATA`
on `/tmp` (tmpfs). On every cold start the bootstrap re-runs and the
runtime tables are empty. This is fine: the bot's *reference data* is
read-only and re-derivable, and *session data* is short-lived per eval
run (the simulator persists transcripts on its side anyway).

## 3. Policy

### Refund matrix (`app/policies/refund_matrix.py`)

The deterministic core: `(intent, order, customer) → (refund%, method,
complaint_target)`.

| Intent | Base | Method | Partner complaint |
|---|---|---|---|
| `missing_item` | 50% | wallet_credit | restaurant |
| `wrong_order` | 100% | wallet_credit | restaurant |
| `cold_food` | 30% | wallet_credit | restaurant |
| `never_arrived` | 100% | wallet_credit | rider |
| `rider_late` | 10% | wallet_credit | rider |
| `rider_rude` / `rider_demanded_tip` | — | — | rider |
| `double_charge` | — | — | app |
| `promo_failed` | 10% | wallet_credit | app |

A tier multiplier scales the base amount: gold +0.15, customers with
>100 orders +0.10, flagged abusers −0.30, clamped to `[0.5, 1.3]`. Stage
2 rewrites Stage 1's amount and method to the matrix value for
matrix-actionable intents on clean customers. The LLM is not trusted to
derive the number from prose — it drifts.

### Abuse signals (`app/policies/abuse_rules.py`)

`is_likely_abuser` fires on **any** of:

- `account_age_days < 30` AND `total_complaints >= 2` — brand-new account
  already complaining.
- `complaint_rate > 0.5` AND `rejected_complaint_rate > 0.5` — historical
  pattern of rejected claims.
- `refunds_30d_total_inr > 2000` AND (`rejected_complaint_rate > 0` OR
  `refunds_30d_count >= 4`) — money-flooded *with* a corroborating signal.

The corroboration on the third rule was added after the prod run (see
§5). Bare high spend with zero rejection history was tripping the
heuristic on legitimate gold-tier customers and producing false abuse
flags on real complaints.

### Stage 2 enforcement (the deterministic layer)

Inside Stage 2, Stage 1's proposal flows through 14 enforcement steps in
order. Each step either *adds*, *strips*, or *rewrites* an action; later
steps see what earlier steps left behind.

```
   Stage 1 proposal: actions[], reasoning, confidence
            │
            ▼
   ┌───────────────────────────────────────────────────────────────┐
   │  CLOSE-marker shortcut  ── customer typed "CLOSE: ..."        │
   │                            → return [close], done             │
   ├───────────────────────────────────────────────────────────────┤
   │  Cap each refund ≤ order.total_inr                            │
   ├───────────────────────────────────────────────────────────────┤
   │  Intent force-routes                                          │
   │    double_charge       → drop refund, force app complaint     │
   │    promo_failed (<24h) → wallet credit (10%) + app complaint  │
   │    cancel_request      → clear all actions (→ app flow)       │
   │    human_request       → T1 with no order: strip escalate     │
   │                          T2+ with human keyword: escalate     │
   │    rider_demanded_tip  → drop refund, force rider complaint   │
   ├───────────────────────────────────────────────────────────────┤
   │  Abuser + never_arrived  → strip refund, escalate, flag       │
   ├───────────────────────────────────────────────────────────────┤
   │  Abuser + cold_food/missing_item                              │
   │     → token credit (≤₹300) + escalate + flag                  │
   │       (rubric prefers small credit + escalate over refusal)   │
   ├───────────────────────────────────────────────────────────────┤
   │  Prompt injection                                             │
   │     → strip refunds for non-refundable intents                │
   │     → always emit flag_abuse                                  │
   ├───────────────────────────────────────────────────────────────┤
   │  Verbal abuse / chargeback threat → escalate calmly           │
   ├───────────────────────────────────────────────────────────────┤
   │  Awaiting order_id (T1, matrix-actionable, clean)             │
   │     → strip premature escalate, stay in prose-ask mode        │
   ├───────────────────────────────────────────────────────────────┤
   │  Matrix proposer (clean customer, Stage 1 only escalated)     │
   │     → swap in refund + partner complaint from matrix          │
   ├───────────────────────────────────────────────────────────────┤
   │  Matrix amount override                                       │
   │     → rewrite Stage 1's refund amount to matrix value         │
   │     → add matrix's partner complaint if Stage 1 missed it     │
   ├───────────────────────────────────────────────────────────────┤
   │  Cross-turn dedupe                                            │
   │     → drop file_complaint / issue_refund already emitted      │
   │       earlier in this session                                 │
   ├───────────────────────────────────────────────────────────────┤
   │  Post-injection pivot (prior turn fired flag_abuse)           │
   │     non-abuser → escalate + flag                              │
   │     abuser     → strip money + escalate, keep only flag       │
   ├───────────────────────────────────────────────────────────────┤
   │  Confidence < 0.6  OR  refund > ₹1500 (and not gold+clean)    │
   │     → downgrade to escalate                                   │
   ├───────────────────────────────────────────────────────────────┤
   │  Already-escalated collapse                                   │
   │     → if no new resolution, replace re-escalate with close    │
   ├───────────────────────────────────────────────────────────────┤
   │  Safety net                                                   │
   │     empty actions  → close   (or escalate+flag if abuser)     │
   └───────────────────────────────────────────────────────────────┘
            │
            ▼
   final actions[]  →  Stage 3 (prose), persist, simulator
```

Each step is one or two `if`-blocks in `app/l2_agents/stage2_validator.py`,
covered by `tests/test_stage2_validator.py` (60 unit tests, runs offline).

### Stage 3 responder (prompt-level rules)

- Never reveal bot / policy / internal scores verbatim.
- Never volunteer money the customer didn't ask for.
- Short, human-sounding, 1–3 sentences.
- **CLOSE HARD RULE:** when `close` is in `validated_actions`, no follow-up
  questions, no "let me know if...", no open-ended invitations. Wish
  them well and end.
- **Don't repeat the prior bot message** — `prior_bot_message` is in
  context; the new reply must reference details from the current
  customer message (order number, item, amount).

## 4. Evals

### Prod run (graded)

One pass through all 22 graded scenarios on Anthropic Sonnet 4.6 + Haiku
4.5. The simulator's `/v1/candidate/summary` is the authoritative score.

| Metric | Value |
|---|---|
| Scenarios completed | 22 / 22 |
| **Aggregate score** | **1960 / 2200 = 89.1%** |
| Perfect-score scenarios | 14 / 22 |
| Strict-mode pass rates | |
| &nbsp;&nbsp;`refund_correct` | 18 / 19 |
| &nbsp;&nbsp;`within_policy_cap` | 19 / 19 |
| &nbsp;&nbsp;`complaint_handling` | 16 / 19 |
| &nbsp;&nbsp;`abuse_handling` | 18 / 19 |
| &nbsp;&nbsp;`escalation_correct` | 15 / 19 |
| &nbsp;&nbsp;`closed_cleanly` | 19 / 19 |
| Partial-credit scenarios | 8: 100, 9: 60, 18: 30 |

`abuse_handling` 18/19 and `closed_cleanly` 19/19 are the architectural
payoff: every iron rule (refund cap, double-charge routing, abuser+never-
arrived refusal, injection stripping, CLOSE-marker short-circuit) is a
deterministic Python branch that fires every time, regardless of what
the customer types or how the LLM phrases its proposal.

### Per-scenario post-mortem (8 failures)

After the run, every failing scenario's transcript was pulled from the
persisted `turns` table and root-caused:

| Sc | Score | Failure | Root cause |
|---|---|---|---|
| 2  | 85 | `complaint_handling` | Stage 1 proposed refund only; matrix rewrote the amount but didn't add the restaurant complaint. |
| 3  | 30 | refund/complaint/abuse/escalation | Aryan (gold, ₹2138 in 3 events, no rejections) was wrongly flagged abuser by `refund_flooded`. Bot escalated+flagged a legitimate complaint. |
| 9  | 60 | partial — refuse+escalate matched 0.6 | Abuser raising plausible cold-food complaint. We refused entirely; rubric rewards small credit + escalate (1.0). |
| 12 | 85 | `complaint_handling` | Same shape as Sc 2 — refund issued, rider complaint dropped. |
| 18 | 30 | partial — full refund matched 0.3 | Abuser claimed never-arrived against "low-quality" rider; existing refusal rule required clean rider, so we caved to pressure and refunded ₹1325. |
| 19 | 90 | `escalation_correct` | Abuser + injection pivot. We escalated; rubric wants quiet refusal + flag (escalation is over-routing for known abusers). |
| 20 | 90 | `escalation_correct` | "Put me through to a manager" on T1. We escalated immediately; rubric wants a triage attempt first. |
| 21 | 90 | `escalation_correct` | Customer said "can you escalate it that way" (a routing request). The regex caught "escalate" as a human-keyword. |

### Post-mortem fixes shipped (live, but not re-graded)

Seven deterministic Stage 2 fixes target the failures above. They are
committed, tested, and live on the Cloud Run URL. They could not be
re-evaluated because the prod simulator's 22-scenario quota was already
consumed by the original run.

| Fix | Mechanism | Targets | Expected delta |
|---|---|---|---|
| F | Matrix amount-override now also adds the matrix's partner complaint when Stage 1 emitted refund-only. | Sc 2, 12 | +30 |
| G | `refund_flooded` requires a corroborating signal (rejection history *or* 4+ events). Bare high spend no longer flags. | Sc 3 | +70 |
| H | Abuser + cold_food/missing_item with order → token credit (≤₹300) + escalate + flag, instead of pure refusal. | Sc 9 | +40 |
| I | Abuser + never_arrived strips refund regardless of rider profile. The "low-quality rider" loophole is closed. | Sc 18 | +70 |
| J | Post-injection-pivot for abusers refuses silently (strip money + escalate, keep only flag). | Sc 19 | +10 |
| K | Drop bare `escalat\w*` from the human-request keyword regex; "escalate it that way" no longer matches. | Sc 21 | +10 |
| L | T1 `human_request` with no order strips Stage 1's escalate to force a triage turn. | Sc 20 | +10 |

Theoretical ceiling after fixes: 100% (2200/2200). Realistic estimate
after accounting for unforeseen interactions: **95–98%**, but the locked
prod number is 89.1% and that's the score on record.

## 5. Limitations

- **The 89.1% is locked.** The prod run consumed the simulator's
  22-scenario quota before the post-mortem fixes shipped. The current
  deployed code would score higher; we have no way to prove that against
  the official grader.
- **Localisation.** Responses are English-only; real Indian
  food-delivery customers type Hindi/English mixed code. The smart-tier
  model handles that fine on input, but the policy text and stage
  prompts are English, so output stays English.
- **Single-instance Cloud Run.** Bundled Postgres on tmpfs forces
  `max-instances=1`. For real production traffic, the right answer is
  Cloud SQL + multi-instance — straightforward to wire, but unnecessary
  for this eval workload.
- **Replay UX.** All 8 failures were diagnosed by `psql`-ing the
  persisted `turns` table; that worked in ~10 minutes. A diff UI against
  the simulator's `/transcript` endpoint would speed up future iteration
  but isn't a current bottleneck.

## 6. Tools used

- Claude Code as the coding assistant.
- Runtime LLMs (provider-agnostic — flip `LLM_PROVIDER`):
  - **In production:** Anthropic SDK. `claude-haiku-4-5` for Stage 0,
    `claude-sonnet-4-6` for Stages 1 and 3.
  - During iteration: Gemini Gateway (free tier).
    `gemini-2.5-flash-lite` for Stage 0, `gemini-2.5-flash` for Stages 1
    and 3.
- No third-party LLM framework (no LangChain / LlamaIndex / DSPy).
  Direct HTTP / SDK calls only.
- 60 unit tests across the deterministic layers (`pytest tests/`).
