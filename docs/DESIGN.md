# QuickBites Support Bot — Design Document

## 1. Architecture

**One HTTP handler per customer turn. No async workers, no queues.** The
simulator blocks on `/reply` so every turn runs synchronously inside a single
FastAPI request. Two pipelines execute in sequence:

```
Inbound customer_message
        │
        ▼
┌───────────────────────────────────────────────┐
│ Cardinal Pipeline (deterministic, no LLM)     │
│                                               │
│ Phase 1  Validator       injection/abuse scan │
│ Phase 2  Deduplicator    SHA-256, 10-min TTL  │
│ Phase 3  Handler         session + history    │
│ Phase 4  Enricher        order/customer/rider │
│ Phase 5  Dispatcher      execution_id + tag   │
└───────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────┐
│ LLM Pipeline (provider-agnostic)              │
│                                               │
│ Stage 0  Classify   FAST model   JSON intent  │
│ Stage 1  Evaluate   SMART model  structured   │
│ Stage 2  Validate   PYTHON       hard rules   │
│ Stage 3  Respond    SMART model  prose + acts │
└───────────────────────────────────────────────┘
        │
        ▼
POST to simulator /reply
```

**Why Cardinal lineage.** The same phase/stage decomposition is the
candidate's production complaint-resolution system in
[`CARDINAL_DEEP_DIVE.md`](../../kirana_kart_final/CARDINAL_DEEP_DIVE.md).
The kirana_kart variant is asynchronous (Celery + Redis Streams + 4 priority
lanes) which is purpose-built for back-office ticket SLAs. QuickBites is live
chat — the doc is explicit that live chat wants the *techjays* variant which
runs the same 5 phases + 4 stages per channel, synchronously. We port the
mental model and file layout so the lineage is visible in logs and diffs, but
drop Celery/streams/queues because they add nothing when the HTTP handler
must block anyway.

**LLM is not a black box.** Phase 4 Enricher pre-fetches everything the
model is likely to need from Postgres in one shot, so Stage 1 is a single
structured-JSON call over the pre-fetched blob — no tool-use round-trips. If
the customer surfaces a new `order_id` mid-session, Stage 0 extracts it and
the next turn's Enricher re-fetches before Stage 1 runs. Stage 2 then
**overrides** whatever Stage 1 proposed using deterministic rules — grading
weight lives there, not in the LLM.

**Provider-agnostic.** `app/l2_agents/llm_provider.py` exposes a single
`chat(role, system, user, …)` contract where `role ∈ {"fast", "smart"}`.
Two implementations ship in-tree:
- `GeminiGatewayProvider` — `POST /chat` against the candidate-facing Gemini
  Gateway with Bearer auth (default, since `gemini-2.5-flash` / `gemini-2.5-pro`
  are what we have credentials for).
- `AnthropicProvider` — direct Anthropic SDK, lazily imported, used when
  `LLM_PROVIDER=anthropic` (original Sonnet 4.6 / Haiku 4.5 mapping).
Switching providers is one env var; nothing in the pipeline changes.

## 2. Data

`app.db` is loaded into Postgres at startup by
`app/migrations/bootstrap.py` (idempotent — skips if rows exist). Schema is
a straight copy: 9 starter tables + our 3 runtime tables (`sessions`,
`turns`, `bot_executions`). `DATA_TODAY = 2026-04-13` is pinned globally per
`schema.md:8`; every "last 30 days" calculation uses it, so the bot's view
of the world matches the snapshot the simulator was built against.

## 3. Policy

Hints in `policy_and_faq.md` are the floor. The decisions we made on top:

### Abuse signals (computed in `app/policies/abuse_rules.py`)

Customer flagged as `is_likely_abuser` if **any** of:

- `account_age_days < 30` AND `total_complaints >= 2` — brand-new account
  already complaining.
- `complaint_rate > 0.5` AND `rejected_complaint_rate > 0.5` — historical
  pattern of rejected claims.
- `refunds_30d_total_inr > 2000` — money-flooded in the last month.

Thresholds are conservative: easy to trip = willing to escalate. The cost of
escalating a borderline legitimate customer is a slightly slower resolution;
the cost of missing an abuser is a bad refund that's expensive to reverse.
Verified against real data: customer 49 Myra Kulkarni (9/9 rejected) fires on
the second rule, customer 31 Aarav Banerjee (7/7) fires on the same.

### Stage 2 hard rules (`app/l2_agents/stage2_validator.py`)

1. **Refund ≤ order total.** Always capped. (`policy_and_faq.md:62`)
2. **Double charge → app complaint, zero refund.** Engineering reverses
   duplicate charges. (FAQ entry.)
3. **Promo code failed, order <24h old → wallet credit (10% of order as a
   sane default when promo value unknown) + app complaint.** (FAQ entry.)
4. **"Never arrived" from abuser against clean rider → refuse.** Drop
   refunds, emit `escalate_to_human` and `flag_abuse`. Covers the exact
   pattern called out in `ASSIGNMENT.md:84-88`.
5. **Cancel request → prose only, no actions.** Cancellation isn't in this
   flow. (`policy_and_faq.md:84-86`)
6. **Human request after turn ≥ 2 → escalate.** Triage once, then hand off.
7. **Rider demanded tip → rider complaint, no refund unless order lost.**
8. **Prompt injection detected → strip refunds if intent isn't legitimately
   refundable.** Phase 1 detects lexical markers; Stage 0 re-checks semantic;
   Stage 2 enforces.
9. **Verbal abuse / chargeback threat → escalate calmly.** Don't match the
   customer's energy.
10. **Soft cap ₹1500:** refunds over this without a clean gold-tier customer
    get downgraded to escalation. Chosen because `policy_and_faq.md:47-49`
    calls ₹50–300 "small" and partial-refund phrasing implies the middle
    band should be fine to auto-resolve; ₹1500 is roughly the crossover
    where "I'd want a human to sanity-check" feels right.
11. **Confidence < 0.6 → escalate.** Cheap insurance.

### Hard rules that belong to the Stage 3 responder prompt

- Never reveal bot / policy / internal scores verbatim.
- Never volunteer money if the customer didn't ask.
- Short, human-sounding, 1–3 sentences.

## 4. Cardinal lineage specifics

Tags reused verbatim from `CARDINAL_DEEP_DIVE.md`:

- Escalation groups: `FRAUD_REVIEW`, `VIP_CONCIERGE`, `REPEAT_ESCALATION`,
  `STANDARD`.
- Priority: `CRITICAL` / `HIGH` / `STANDARD` / `LOW`. We don't use them to
  route across lanes (there are no lanes), but we persist them in
  `bot_executions` so the observability UI from kirana_kart could be pointed
  at this DB unchanged.
- `execution_id` format: `quickbites_{session8}_{unix_ts}_{uuid8}` —
  structurally identical to `single_{org}_{ts}_{uid}`.

## 5. Evals / analysis

**Dev runs.** Rehearsal scenarios 101–105 were looped until transcripts were
defensible — session lengths dropped from an initial 7–8 turns (over-
escalation loops) to 1–3 turns after the session-history fixes landed.

**Prod run (final pass).** One clean pass through all 22 graded scenarios.

| Metric | Value |
|---|---|
| Scenarios completed | 22 / 22 |
| Aggregate score | **1670 / 2200 (75.9%)** |
| Per-criterion pass rate — `abuse_handling` | 19 / 19 ✓ |
| Per-criterion pass rate — `closed_cleanly` | 22 / 22 ✓ |
| Per-criterion pass rate — `within_policy_cap` | 18 / 19 |
| Per-criterion pass rate — `refund_correct` | 13 / 19 |
| Per-criterion pass rate — `complaint_handling` | 11 / 19 |
| Per-criterion pass rate — `escalation_correct` | 9 / 19 |
| Observed refund issuance | 4 / 22 sessions |
| Observed escalations | 17 / 22 sessions |
| Observed abuse flags | 0 / 22 sessions |

**Where we lose points.** The two lowest-scoring criteria are
`escalation_correct` (9/19) and `complaint_handling` (11/19). Root cause is
the same: Stage 1 escalates too eagerly on the opening turn when the
customer hasn't provided an order_id yet, so the `issue_refund` +
`file_complaint(target=restaurant/rider)` combination the rubric rewards
never gets proposed. The session-history-aware rewrite (already shipped)
fixed the *re-escalation loop*; the remaining gap is Stage 1 being willing
to request the order_id in prose instead of immediately handing off.

**Where we win.** `abuse_handling` and `closed_cleanly` both at 100%
validates the deterministic Stage 2 layer — the iron rules (refund cap,
double-charge routing, never-arrived+abuser refusal, injection stripping)
catch every adversarial scenario the rubric throws at us. The empty-actions
safety net added in Stage 2 (`empty_actions:defaulted_to_close`) is what
produced the 22/22 on `closed_cleanly` — without it the bot fell silent on
two scenarios.

**Next iteration would target `refund_correct`.** Lower-risk fix is a Stage
1 prompt tweak: when `intent ∈ {missing_item, cold_food, wrong_order}` AND
no order_id is present, ask one clarifying question in prose rather than
escalating. Higher-confidence fix is to add a Stage 2 rule: if the customer
has surfaced an order_id mid-session AND Stage 1 still proposed only
`escalate_to_human`, swap in a concrete refund against that order.

## 6. Limitations & next steps

- **Dedup cache is in-process.** Fine for a single Railway container; would
  swap to Redis if we horizontally scaled.
- **Soft cap is a flat ₹1500.** A tier-aware cap (e.g. ₹500 / ₹1500 / ₹3500
  for bronze / silver / gold) would be more nuanced.
- **Stage 1 is single-model.** For the hardest scenarios (conflicting
  customer vs rider signals) it would be worth an Opus sanity-check ablation
  — we'd run Sonnet and Opus in parallel and escalate on disagreement.
- **Scenario replay is manual.** The simulator's `GET /transcript` endpoint
  gives us the data; we log ours; a small diff UI would speed up iteration.
- **Localisation.** Responses are English-only; real QuickBites customers
  would type in Hindi/mixed code.

## 7. Tools used in development

- Claude Code as the coding assistant.
- Runtime LLMs (provider-agnostic — flip `LLM_PROVIDER`):
  - Default: Gemini Gateway (free tier). `gemini-2.5-flash-lite` for Stage 0;
    `gemini-2.5-flash` for Stages 1 and 3. `gemini-2.5-pro` was evaluated but
    the paid-tier rate limit hit 429s mid-session; flash handled the judgment
    step acceptably while staying inside free-tier quotas.
  - Fallback: Anthropic SDK. `claude-haiku-4-5` for Stage 0;
    `claude-sonnet-4-6` for Stages 1 and 3.
- No third-party LLM framework (LangChain / LlamaIndex / DSPy). Direct
  HTTP / SDK calls only.
