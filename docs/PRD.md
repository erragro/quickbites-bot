# Sreshtha — Product Requirements Document

**Version:** 0.1 (draft — for Meet the Builders submission)
**Owner:** Surajit Chaudhuri (solo builder)
**Last updated:** 2026-08-13
**Submission target:** Google "Meet the Builders" APAC campaign, Gen AI Academy track
**Deadline:** ~2026-09-02 (20 days from finalisation)

---

## 1. Executive summary

**Sreshtha** (श्रेष्ठ / শ্রেষ্ঠ / சிரேஷ்ட — Sanskrit for "the best" / "supreme") is a mobile-first web platform that gives Indian gig workers access to their rights, their contracts, and the government schemes they're already entitled to — in their own language, at literacy levels the market currently ignores.

India has 7.7 crore gig workers today, projected to hit 23.5 crore by 2030 (NITI Aayog 2024). Every major platform onboards them in English or Hindi only. Contracts are legalese. Complaints go nowhere. Rights are undocumented. Newly-recognised social security under the Code on Social Security 2020 is discretionary and access-gated.

Sreshtha is five integrated modules on a common conversational surface:

1. **Contract Reader** — upload the contract you signed, get it translated and explained clause-by-clause in your language
2. **Rights Guide** — curated fact cards on wages, safety, insurance, dismissal, and grievance rights
3. **Chatbot (Sahaayak)** — natural-language Q&A over your rights + your uploaded documents, retrieval-first, with citations
4. **Schemes Finder** — three-question decision tree that surfaces every state + central scheme you're eligible for
5. **Complaint Helper** — draft a formal complaint in your language, routed to the right authority (Labour Commissioner, e-Shram grievance cell, platform CX, or India Labourline)

Delivered through a multi-tenant SaaS shell (platforms, unions, and welfare boards can license their own configurations) with worker-facing UX designed for voice input, icon navigation, and offline-first content access.

Three integrated bets:
- **Social impact** — a large, underserved workforce with no equivalent tool today
- **AI-first vertical platform** — Gemini + Sarvam handling six Indic languages natively, with deterministic Python owning every high-stakes decision
- **B2B2C SaaS** — worker-facing but sold to gig platforms, aggregators, unions, and state welfare boards under compliance framings

---

## 2. Problem statement

### 2.1 The workforce

- **7.7 crore gig workers in India today** (NITI Aayog, 2024)
- **23.5 crore projected by 2030** — 6.7% of the total non-agricultural workforce
- **Language distribution**: Hindi ~40%, Bengali ~8%, Tamil ~6%, Telugu ~7%, Marathi ~7%, Kannada ~4%, other Indic ~28%, English-first <1%
- **Bengali migrant concentration**: heavy in Delhi NCR, Bangalore, Mumbai, Chennai, Pune, Hyderabad — construction, delivery, sanitation, domestic work
- **Median age**: 27 (Ola Mobility Institute)
- **Female participation**: 6-8% (BetterPlace 2024)
- **Rural origin**: 68% (NCAER 2023)

### 2.2 The harm

Documented in Fairwork India reports (IIIT-B / Oxford), IFAT surveys, Ola Mobility Institute studies, and NITI Aayog policy briefs:

- **40% earn under ₹15,000/month** before vehicle costs, fuel, and platform charges
- **90% have no savings**; 78% report household income shocks in any given quarter
- **83% of cab drivers work >10 hours/day**; 50%+ of delivery riders report heat exhaustion
- **Wage theft is widespread** — deducted incentives, disputed cancellations, opaque per-order calculations
- **Contract terms unread** — 92% of workers sign the platform agreement without reading it (IFAT 2023); 88% of those signed a version they cannot re-download
- **Grievance recourse invisible** — 61% don't know they can complain to a labour officer; 78% don't know the e-Shram grievance cell exists

### 2.3 The regulatory framework — new but unused

- **Code on Social Security 2020** — first central law to recognise gig workers as a distinct category. Sections 113–114 mandate scheme design + registration. Rules notified 2024.
- **e-Shram portal** — 30+ crore unorganised workers registered by mid-2024 but only ~4% of gig workers report knowing what benefits attach to their registration
- **Karnataka Platform-Based Gig Workers (Social Security and Welfare) Ordinance 2025** — first state-level welfare board. 1-2% cess on transactions.
- **Rajasthan Platform-Based Gig Workers (Registration and Welfare) Act 2023** — Rajasthan Platform Based Gig Workers Welfare Board established.
- **Central Motor Vehicles Rules amendment (2024)** — aggregator responsibility for driver welfare on safety training + insurance
- **Consumer Court + Labour Court dual pathway** — either channel can hear wage disputes; almost nobody knows this

The gap: **workers don't know these mechanisms exist, don't know how to activate them, and don't have anyone translating the letter of the law into "here's what to do this afternoon."**

### 2.4 What exists today (and why it's insufficient)

| Tool | What it does | Why it doesn't close the gap |
|---|---|---|
| **e-Shram portal** | Registration + UAN issuance | Registration-only; benefits are downstream and unclear; UI is English/Hindi only, desktop-first |
| **Namma Yatri** | Alternative ride booking for Bangalore autos | Solves the platform-lock problem for one city, one modality; no rights/legal layer |
| **Kaam.com / Apna** | Job discovery | Discovery only; nothing about the terms you're signing |
| **Union WhatsApp groups (IFAT, All India Gig Workers Union)** | Peer support, protest coordination | Depend on human moderators; no scale, no persistence, no linguistic coverage beyond leader's language |
| **Fairwork India reports** | Annual grading of platforms | Advocacy tool for policymakers, not usable by workers |
| **State welfare board portals** | Scheme registration | Vary wildly; opaque eligibility; scheme discovery near-impossible |

No consolidated worker-facing product exists in the market today. The closest analogue is Fairwork India, which is a research and advocacy vehicle, not a product.

---

## 3. Target users

### 3.1 Primary persona — Rahul, delivery rider, Bangalore

- 24, moved from Balrampur (UP) 18 months ago
- Speaks Hindi natively, some Bhojpuri, functional English for basic app UX
- Works Swiggy + Zomato + Rapido, 11-hour days, ₹18-22k/month before petrol
- Signed contracts he cannot recall
- Owes a friend ₹8,000 from last month's medical bill for a fall on delivery
- Wants: to know if the platform owes him for the days off after the accident, and to file a complaint if it does
- Phone: 3-year-old Redmi, 3G data, WhatsApp + Instagram Reels heavy user, uses voice search on Google

**What he does today**: asks the union WhatsApp group, gets vague answers back in a mix of Hindi and English, gives up.

**What Sreshtha does for him**: he uploads a screenshot of his contract, gets the injury-related clauses explained in Hindi voice + text, sees a fact card on "compensation for platform work injuries," and lands on a pre-filled complaint template for the Karnataka Platform Welfare Board.

### 3.2 Secondary persona — Sabina, domestic worker, Bengaluru

- 38, from Murshidabad district (WB), migrated 6 years ago
- Speaks Bengali natively, functional Hindi, no English
- Works through Urban Company + one private household
- Has never seen a written contract; verbal agreement with Urban Company documented only in app
- Wants: to know if she is on the e-Shram register (she doesn't remember signing up), and to understand what happens if she gets injured on the job

**What she does today**: nothing. Assumes nothing exists.

**What Sreshtha does for her**: voice-first Bengali onboarding. Sreshtha checks her e-Shram status via UAN lookup, walks her through what social security she's entitled to under the Karnataka Ordinance, and helps her file the missing registrations.

### 3.3 Tertiary persona — Muthu, driver, Chennai

- 32, native Tamil speaker, Ola driver + occasional truck runs
- Reads Tamil, some English signs
- Wants: a straight answer on whether the platform's ₹1 lakh insurance claim actually pays for the vehicle damage from last month
- Uses YouTube in Tamil for everything he doesn't understand about his work

**What Sreshtha does for him**: he uploads the insurance denial letter, gets the reason explained in Tamil, is shown the ombudsman escalation pathway with a pre-filled complaint template.

### 3.4 B2B buyers (secondary, post-demo)

- **Gig platforms** looking to demonstrate Fairwork India compliance
- **State welfare boards** rolling out worker-facing benefit discovery
- **Unions** (IFAT, All India Gig Workers Union) using it as member service
- **CSR arms of large corporates** (Tata, Mahindra) funding worker education programs

Not the audience for v1. But the tenant model is designed so this is a straight-line evolution, not a rewrite.

---

## 4. Product vision & principles

### 4.1 Vision

**Every gig worker in India should be able to understand their contract, know their rights, and file a complaint that goes somewhere — in their own language, from their own phone, in under five minutes.**

### 4.2 Principles (ranked)

1. **Language-first.** Bengali, Tamil, Hindi are first-class; English is a fallback for the platform, not the norm. Every screen defaults to the worker's language.
2. **Voice-first, then icon-first, then text.** Reading is the last resort. ASR + TTS on every meaningful interaction. Icons carry navigation.
3. **Deterministic where it matters, generative where it helps.** Rights facts, scheme eligibility, complaint routing, template filling — all in Python. LLMs handle language understanding + tone. Never LLM-drafted legal advice.
4. **Cite everything.** Every claim shows its source (statute name + section, or scheme document). Every chatbot answer shows what it retrieved.
5. **Trust signals throughout.** Government logos when linking to official portals. Explicit "not legal advice" framing. Union endorsement on the roadmap.
6. **Offline-capable content.** Rights Guide + uploaded contracts remain readable when the network dies. Complaint drafts sync when connectivity returns.
7. **Lite-mode default.** Assumes 3G / 2G. Aggressive image + audio compression. Progressive enhancement, not degradation.
8. **No password fields.** OTP or biometric only. Typing passwords is a barrier we can eliminate.
9. **Worker-owned data.** Uploaded contracts and complaint drafts belong to the worker. Deletion is one tap.
10. **Warm, human tone.** No corporate register. No "we regret to inform you." No em dashes. No "frustration" language. Every string in every language passes the same tone lint.

---

## 5. Solution overview

Sreshtha is one shell hosting five modules, all reachable through the same left sidebar, the same chatbot, and the same user account.

### 5.1 The shell

Already built (from the QuickBites substrate, now being rebranded):

- **Auth** — email + password today; migrating to OTP-first before submission
- **Session management** — chat sessions with title, history, rename, delete
- **Module registry** — modules can be registered by super-admin and gated per-user
- **Tenant configuration** — business units + issue types + response templates, admin-editable
- **Chat pipeline** — Cardinal-inspired synchronous 5-phase + 4-stage design, deterministic Stage 2 rule enforcement
- **LLM abstraction** — Gemini (Vertex AI) for en/hi, Sarvam for all other Indic languages, auto-routed by detected language
- **Admin panel** — user + access matrix, module + tone-spec editing

### 5.2 The five modules

Each is a first-class module registered in the shell. Access levels: view / edit / admin (workers get `view` on all; NGO admins get `edit` on Rights Guide; super-admin manages everything).

1. **Contract Reader** (anchor for demo) — upload contract PDF or image → OCR → three-stage translation (understand → research → synthesise, from the `thought-translate` prior art) → clause-by-clause explanation with rights implications flagged
2. **Rights Guide** — curated fact cards on 15+ topics × 3 languages (Hindi, Bengali, Tamil for v1); each card is a short summary + statute/scheme citation + "what to do about it" action
3. **Chatbot (Sahaayak, सहायक — "helper")** — the existing chat surface, retargeted. RAG over Rights Guide + uploaded user documents. Retrieval-first (deterministic answers from the library); LLM fallback for unmatched intents.
4. **Schemes Finder** — three-question wizard (state + occupation + demographics) → list of matching schemes with eligibility + apply-link + document checklist
5. **Complaint Helper** — pick a topic (wage / injury / dismissal / harassment / insurance) → template fill (voice or text) → language-appropriate output → route to the right authority (Labour Commissioner / e-Shram / platform CX / consumer court / Labourline)

### 5.3 What's already usable, what's not

| Component | State | 20-day work needed |
|---|---|---|
| Auth (email/password) | Working | Add OTP-first login |
| Session CRUD | Working | Rebrand; keep |
| Chat pipeline | Working (Gemini for all languages after 2026-08-15 pivot) | Retarget prompts + Stage 2 rules for gig-worker domain |
| Admin panel | Working | Retarget; add module-specific admin pages |
| Language routing | Working (Gemini-only for reasoning; Sarvam Mayura for translation only) | Verify Bengali + Tamil quality; add ASR/TTS; add script-flip toggle |
| **Contract Reader** | Not built | Full build — OCR + three-stage translation UI |
| **Rights Guide** | Not built | Content curation (15 cards × 3 languages) + browsing UI |
| **RAG for chatbot** | Not built | Vector index over Rights Guide + docs |
| **Schemes Finder** | Not built | Decision tree + scheme database (10 schemes for demo) |
| **Complaint Helper** | Not built | Template library + authority directory |
| Voice input | Not built | Sarvam ASR on chat + form fields |
| Voice output | Not built | Sarvam TTS on chatbot responses + fact cards |
| Landing page | Wrong brand | Rewrite for Sreshtha |

---

## 6. Module specifications

For each module: purpose, v1 scope (what ships for demo), v2 scope (post-submission), and non-goals.

### 6.1 Contract Reader

**Purpose**: replace "signed something I couldn't read" with "understood every clause that matters to me."

**v1 (demo)**:
- Upload PDF or image (up to 10MB)
- OCR via Gemini vision (or Sarvam OCR if quality lags)
- Three-stage LLM processing:
  1. **Understand** — extract clauses, identify contract type (aggregator / labour / vendor)
  2. **Research** — flag clauses that reference statutes; annotate with Indian labour law context
  3. **Synthesise** — output a rendered document in the worker's language with plain-language explanations underneath each clause
- Highlighting for the worker: **red** (adverse — cancellation without notice, unilateral deduction, indemnification), **amber** (worth knowing — non-compete, exclusivity), **green** (favourable — insurance, PF)
- "Ask about this clause" button opens the chatbot with that clause pre-loaded as context
- Downloadable annotated PDF (for taking to a labour officer if needed)
- Three sample contracts pre-loaded in demo (Swiggy delivery T&C, Ola Cabs onboarding, Urban Company partner agreement) so a reviewer can play with it without uploading

**v2 (post-demo)**:
- Contract version tracking (worker uploads updates over time; deltas surfaced)
- Multi-worker signals ("500 workers who signed this same contract found clause 4.2 problematic")
- Legal aid referral (partner with NGOs / bar council pro bono cells)
- Contract negotiation prep — talking points for asking for changes

**Non-goals**:
- Legal advice. All output ends with "this is not a substitute for professional legal advice; contact India Labourline (1800-419-1550) for formal help."
- Contract drafting. We read, we don't write.

### 6.2 Rights Guide

**Purpose**: give workers a canonical, curated, cite-able answer to "what am I entitled to?"

**v1 (demo)**: 15 fact cards × 3 languages (Hindi, Bengali, Tamil) + English source:

Topics:
1. **Minimum wage** — what applies to gig workers vs. what doesn't
2. **Injury on the job** — what compensation, what claim process
3. **Insurance under the platform** — reading policy terms, filing claims, denials
4. **Dismissal / deactivation** — notice, appeal, arbitration
5. **Harassment** — what to do, where to report, POSH Act applicability
6. **Wage theft** — what counts, what recourse
7. **Working hours + rest** — WHO/ILO guidance vs. Indian statute
8. **Contract fairness** — Fairwork India's five principles
9. **E-Shram registration** — who, why, what happens after
10. **Karnataka Welfare Cess** — what it means for KA workers
11. **Rajasthan Gig Workers Welfare Board** — how to register
12. **Consumer court vs. labour court** — when to use which
13. **India Labourline (1800-419-1550)** — what it's for, what to expect
14. **PF and ESIC** — applicability to gig workers under new codes
15. **Grievance escalation** — the full ladder from platform CX to labour commissioner

Each card:
- 3-paragraph plain-language summary
- Statute / scheme / policy citation with link
- "What to do about it" — 3 concrete actions
- "Ask about this" opens chatbot with the card as context
- Audio version (Sarvam TTS)
- Downloadable one-pager PDF for offline reference

**v2 (post-demo)**:
- 60 cards
- State-specific variants
- Union endorsement badges
- Video versions (60-second explainers)

**Non-goals**:
- Case law citation (too high-stakes without lawyer review)
- Individual legal advice

### 6.3 Chatbot (Sahaayak, सहायक)

**Purpose**: natural-language interface to the Rights Guide + the worker's own uploaded documents.

**v1 (demo)**:
- Adapts existing Cardinal pipeline
- **Retrieval-first**: every question first hits a vector index over Rights Guide fact cards + uploaded contract clauses. If a card scores >0.75, answer is composed from card + citation.
- **LLM fallback**: if no card matches, Gemini/Sarvam answers with a "this is my best understanding, not verified" disclaimer + a "would you like me to help you file a formal question with a labour officer?" offer
- Voice input via Sarvam ASR
- Voice output via Sarvam TTS on request (tap-to-hear)
- Session persistence — worker can come back to old conversations
- Streaming responses (Phase E work already in progress)
- Language auto-detect, defaults to worker's chosen language

**v2 (post-demo)**:
- Multi-turn context maintenance across sessions ("last time we talked about your Swiggy contract — is this a follow-up?")
- Human handoff to union / NGO volunteers
- Group chat for organising (workers in one platform + one city talking together)

**Non-goals**:
- Legal advice. Same disclaimer as Contract Reader on every response.
- Multilingual code-switching in a single response (each response stays in one language).

### 6.4 Schemes Finder

**Purpose**: a worker should discover in 3 questions every government scheme they are eligible for.

**v1 (demo)**:
- 3-question wizard: state, occupation, demographic factors (age / gender / children / disability)
- 10 schemes indexed for demo:
  1. e-Shram registration
  2. PM Suraksha Bima Yojana
  3. PM Jeevan Jyoti Bima Yojana
  4. Ayushman Bharat PM-JAY
  5. PM Shram Yogi Maandhan (pension)
  6. Karnataka Platform Gig Workers Welfare Fund
  7. Rajasthan Gig Workers Welfare Board benefits
  8. State-specific ration card + Public Distribution
  9. Sukanya Samriddhi (for workers with daughters)
  10. Atal Pension Yojana
- For each match: eligibility summary, documents needed, apply-link (official portal), estimated time to complete
- "Ask about this scheme" opens chatbot with scheme context

**v2 (post-demo)**:
- 40 schemes
- Direct application assistance (form pre-fill where portals allow)
- Application status tracking

**Non-goals**:
- Guaranteeing benefit disbursement — we surface eligibility, we don't process claims

### 6.5 Complaint Helper

**Purpose**: turn "I want to complain" into "I have filed a complaint that will be seen."

**v1 (demo)**:
- Topic picker: wage / injury / dismissal / harassment / insurance / other
- Template chosen based on topic, adaptable
- Voice or text fill for the specifics ("when did this happen, what did they say")
- Language-appropriate output — the complaint is drafted in the language the worker chose, plus English (many portals require English)
- Routing rules:
  - **Wage / dismissal**: state labour commissioner + India Labourline
  - **Injury**: platform CX first (with escalation ladder), ESIC if applicable
  - **Harassment**: Internal Committee under POSH + local police
  - **Insurance**: platform CX + ombudsman
- Copy button, share button (share to WhatsApp), PDF export
- Follow-up reminder — Sreshtha checks back in 7 days: "did you file this? did you hear back?"

**v2 (post-demo)**:
- Direct filing via API for portals that support it (unlikely for most, but Karnataka Welfare Board is a candidate)
- Aggregate complaint dashboard for unions / NGOs
- Legal aid referral

**Non-goals**:
- Guaranteeing action on the complaint
- Representing the worker legally

---

## 7. Technical architecture

### 7.1 High level

```
┌─────────────────────────────────────────────────────────────┐
│                     Worker's phone (web)                    │
│         React 19 + Vite + Tailwind v4 + shadcn/ui           │
│         Bengali / Hindi / Tamil / English UI                │
│         Voice input + TTS output                            │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS + JWT
┌────────────────────────┴────────────────────────────────────┐
│                     FastAPI backend                         │
│  ┌──────────────┬─────────────┬──────────────┬───────────┐  │
│  │   Modules    │  Cardinal   │   Content    │  Voice    │  │
│  │   Registry   │   Pipeline  │   Store      │  Services │  │
│  └──────────────┴─────────────┴──────────────┴───────────┘  │
│         │              │            │            │          │
│    ┌────┴────┐    ┌────┴────┐  ┌────┴────┐  ┌────┴────┐    │
│    │Postgres │    │ Vertex  │  │ Vector  │  │ Sarvam  │    │
│    │(users,  │    │  AI     │  │  index  │  │  ASR +  │    │
│    │content, │    │(Gemini) │  │(pgvector│  │  TTS    │    │
│    │sessions)│    │         │  │  or PC) │  │         │    │
│    └─────────┘    └─────────┘  └─────────┘  └─────────┘    │
│                        │                                    │
│                   ┌────┴────┐                               │
│                   │ Sarvam  │                               │
│                   │  Chat   │                               │
│                   │(Indic)  │                               │
│                   └─────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Key design decisions

**Deterministic where it matters, generative where it helps.**
Every high-stakes decision (which scheme matches, which authority to route to, what a statute says) lives in Python. LLMs handle three things: language detection, clause understanding on uploaded contracts, and warm chat responses when retrieval misses. Nothing binding is generated.

**Retrieval-first chatbot.**
The chatbot's default answer path is: embed the question → retrieve from Rights Guide fact cards + user's uploaded clauses → compose response from retrieval + template. LLM only writes freely when nothing matches — and every miss is logged as a candidate for a new fact card. The response library grows with usage.

**Gemini owns all reasoning and generation; Sarvam is the translator.**

(Architecture pivot on 2026-08-15 after live-testing Sarvam quality and starter-tier limits.)

- **Gemini 2.5 Flash** (Vertex AI, thinking disabled for latency) handles every reasoning + generation call across every language. Gemini handles Hindi, Bengali, Tamil, Telugu, Kannada, Marathi natively at production quality, and giving one provider ownership of all Stage 1-3 output means tone control lives in one prompt per stage. Contract processing goes through Gemini regardless of the detected contract language.
- **Sarvam Mayura v1** is the dedicated translator, used when we need to move curated content across languages (Rights Guide fact cards from English → Hindi/Bengali/Tamil, complaint templates, etc.). It is not on the chat-completion path.
- **Sarvam Transliteration** handles Roman ↔ Devanagari (and equivalent script pairs for other Indic languages) for the form-time script toggle: a worker who reads Hindi fluently only in Roman letters can pick "Roman" before uploading a contract, and Stage 3 output is transliterated to Roman before display.

The `LLMProvider` protocol is retained (the `SarvamProvider` class is kept but no longer wired into `get_provider()`) so a future re-introduction of provider routing needs no interface changes.

**Voice at the edge, chat at the centre.**
Sarvam ASR converts speech to text on the client's turn boundary. That text is what the pipeline sees — no special "voice mode." TTS renders on-demand ("tap to hear this fact card") rather than always-on.

**Multi-tenant from day 1.**
Business units, issue types, response templates, fact cards, complaint templates — all carry a `tenant_id` (nullable for v1 = shared). Post-submission, tenants can override any config without code changes.

**RAG via pgvector, not a vector DB.**
Postgres extension keeps operational surface area small for solo builder. Rights Guide is small (~15-60 cards) so IVFFlat index is fine. If scale demands, switch to Pinecone in v2.

**OCR via Gemini vision.**
For images and low-quality PDFs. Gemini's multimodal is already best-in-class for Indic-script images. Cost is acceptable for v1 volumes.

### 7.3 Three-stage translation reasoning (Contract Reader)

Ported from the `thought-translate` prior art:

**Stage 1 — Understand:**
LLM reads the contract, identifies contract type, extracts clauses, labels legal concepts. No translation yet.

**Stage 2 — Research:**
LLM annotates each clause with references to Indian labour law (Code on Social Security 2020, Motor Vehicles Act aggregator amendments, Fairwork India principles, state gig-worker legislation). Flags clauses that reference or contradict statute. Determines colour code (red/amber/green).

**Stage 3 — Synthesise:**
LLM produces the final worker-facing rendition in the target language: original clause + plain-language explanation + rights implication + suggested action.

Each stage is a discrete LLM call with a strict output schema. Failures don't cascade — a failed Stage 2 falls back to Stage 1-only output ("here's what the contract says, but I couldn't cross-check the law today").

### 7.4 Existing components we're reusing

| Component | From | Retargeting |
|---|---|---|
| Cardinal 5-phase + 4-stage pipeline | QuickBites | Retarget prompts for rights domain |
| Stage 2 deterministic validator | QuickBites | New rule set for rights-domain claims |
| Response template library + linter | QuickBites | New templates for rights answers |
| Language auto-routing | QuickBites | Same |
| Auth + sessions + admin panel | QuickBites | Same |
| Alembic + models | QuickBites | +5 tables (fact cards, schemes, complaints, contracts, embeddings) |

### 7.5 New tables (migration 005)

```
fact_cards         (topic, language, title, body, citation, action)
schemes            (name, state, eligibility_rules_json, apply_url, docs_needed)
complaint_templates(topic, language, template, routing_json)
uploaded_contracts (user_id, filename, storage_key, ocr_text, stages_json)
embeddings         (source_type, source_id, vector, model)
```

---

## 8. UX principles + design system

### 8.1 Language selection

- First screen after landing: language picker (grid of large-tap buttons in each language's own script)
- Chosen language persists in JWT + local storage
- Every module heading + every navigation label + every button in the chosen language
- Language switcher persistent in header (never buried)

### 8.2 Voice

- Every text input has a microphone icon; long-press to record
- Sarvam ASR runs on release; text appears in the field
- Chatbot bubbles have "▶" playback icon; taps read the message in TTS
- Fact cards have a play button at the top; auto-narrates the whole card
- No autoplay — always user-initiated (avoids battery + data blowup, respects public listening)

### 8.3 Icons

- Every module has a Lucide icon (already in `icons.ts` registry)
- Every fact card topic has a Lucide icon
- Colour + shape carry meaning first, text second
- Icon + label pairing is mandatory — icons never appear alone unless the label is 1 word

### 8.4 Tone

Every user-facing string, in every language, passes the lint spec:

- **No em dashes** (`—`); use commas or full stops
- **No negative-emotion vocabulary** ("frustration", "disappointment", "annoying", "furious")
- **No corporate register** ("kindly", "we regret to inform", "as per our records")
- **No policy language** ("as per our terms", "per our guidelines")
- **Warm, direct, informational** — the register of a helpful older sibling
- **Max 3 sentences per response** for chatbot; max 3 paragraphs per fact card

### 8.5 Colour + accessibility

- WCAG AA contrast throughout
- Text sizing minimum 16px; primary buttons 20px+
- Colour never carries meaning alone (adverse-clause red is paired with icon + border pattern)
- Dark mode by default (reduces battery on OLED phones common in this segment)

### 8.6 Offline capability

- Service worker caches Rights Guide fact cards (all 15, all languages) on first load
- Uploaded contracts + their processed renditions cached in IndexedDB
- Complaint drafts saved locally, sync when back online
- Chatbot works offline via retrieval when Rights Guide fact card matches; LLM fallback requires network
- Clear "You're offline — showing saved content" banner

### 8.7 Trust

- Government logos when linking to official portals (e-Shram, Karnataka Welfare Board)
- Every claim shows its citation (statute + section)
- "Not legal advice" footer on every module
- India Labourline (1800-419-1550) prominently displayed on Complaint Helper as the escalation option

---

## 9. Success metrics

### 9.1 Submission metrics (for Google Meet the Builders)

- Working demo URL deployed on Cloud Run
- 3-5 minute demo video showing Contract Reader flow in Hindi + Bengali
- Blog post published (Medium or personal blog)
- All five modules navigable
- Contract Reader anchor flow works end-to-end with pre-loaded sample contract
- Chatbot answers questions in Hindi + Bengali + Tamil with citations

### 9.2 Product metrics (post-submission, first 90 days)

- **Adoption**: 1,000 first-time workers (target)
- **Depth**: 40% complete at least one non-chat action (upload / read fact card / find scheme / draft complaint)
- **Retention**: 20% return in second week
- **Language mix**: 40% Hindi, 15% Bengali, 15% Tamil, 30% other Indic + English
- **NPS**: 40+ (bar: existing platform CX averages 20)
- **Complaint success rate**: 15% of drafted complaints receive a response within 14 days (measured by follow-up prompt)

### 9.3 Business metrics (post-submission, first 6 months)

- 2 pilot partnerships (one platform + one state welfare board or union)
- Monthly recurring revenue: ₹0-2L (early)
- Contract Reader corpus grows to 500+ real contracts

---

## 10. 20-day timeline

Build day 1 = **2026-08-14**. Submission target = **2026-09-02**.

| Day | Track | Deliverable |
|---|---|---|
| **1 (Aug 14)** | PRD + Academy | Finalise this PRD. Register for Gen AI Academy APAC Edition. Rebrand landing page + app title to Sreshtha. |
| **2 (Aug 15)** | Shell rebrand | Sidebar module names, colour palette, favicon, logo. Language picker screen. Retire QuickBites-specific chip tree. |
| **3 (Aug 16)** | Content model | Migration 005 (fact_cards, schemes, complaint_templates, uploaded_contracts, embeddings). Seed 3 fact cards + 3 schemes + 3 complaint templates in EN as scaffolding. |
| **4 (Aug 17)** | Contract Reader — upload | File upload UI. Backend upload endpoint + storage (Cloud Storage). File type validation. |
| **5 (Aug 18)** | Contract Reader — OCR + Stage 1 | Gemini vision OCR. Stage 1 (Understand) LLM call. Persist output. |
| **6 (Aug 19)** | Contract Reader — Stage 2 + 3 | Research + Synthesise stages. Statute annotation. Colour coding logic. |
| **7 (Aug 20)** | Contract Reader — UI | Clause-by-clause viewer. Colour highlights. "Ask about this" hook to chatbot. Download annotated PDF. |
| **8 (Aug 21)** | Contract Reader — Bengali/Tamil | Localise 3 sample contracts (Swiggy Hindi, Ola Tamil, Urban Company Bengali). QA translation quality end-to-end. |
| **9 (Aug 22)** | Rights Guide — content | Write all 15 fact cards in English. Have all 15 translated into Hindi + Bengali + Tamil (Sarvam batch job + human review of top 5). |
| **10 (Aug 23)** | Rights Guide — UI | Card list, card detail view, filter by topic, audio playback (Sarvam TTS). |
| **11 (Aug 24)** | Chatbot — RAG | pgvector setup. Embed all 45 fact card variants. Retrieval + reranking. Wire to Cardinal pipeline as new intent path. |
| **12 (Aug 25)** | Chatbot — retargeting | New Stage 2 rules for rights domain. New response templates. New system prompts for Sahaayak persona. |
| **13 (Aug 26)** | Voice | Sarvam ASR on chat input + Complaint Helper text areas. Sarvam TTS on chatbot messages + fact cards. Latency budget: <500ms round trip. |
| **14 (Aug 27)** | Schemes Finder | 3-question wizard UI. 10 schemes indexed with eligibility rules JSON. Match logic. Apply-link routing. |
| **15 (Aug 28)** | Complaint Helper | Topic picker. 5 complaint templates × 3 languages. Voice/text fill. Authority routing. PDF export + share to WhatsApp. |
| **16 (Aug 29)** | Language + tone pass | End-to-end language QA in Hindi + Bengali + Tamil. Tone lint sweep across all templates. Fix any leaked English strings. |
| **17 (Aug 30)** | Deploy | Cloud Run redeploy under Sreshtha branding. Domain setup if we have one; else Cloud Run URL. Load test — 10 concurrent chats without dying. |
| **18 (Aug 31)** | Video | Script + record 3-5 min demo video. Screen recording of Contract Reader (Hindi) + Chatbot (Bengali) + Schemes Finder + Complaint Helper flows. Voiceover in English for reviewers. |
| **19 (Sep 1)** | Blog + narrative | Write Medium blog post: problem, solution, tech story, what's next. Include the video + demo URL + GitHub link. |
| **20 (Sep 2)** | Submit + buffer | Complete form submission. Post on LinkedIn per campaign instructions. Buffer for slippage on any of days 1-19. |

### Slippage protocol

If Contract Reader slips past day 8 by more than 24 hours → cut Contract Reader's Bengali sample, keep Hindi + Tamil.
If Rights Guide translation slips past day 10 → ship 10 cards not 15.
If Schemes Finder + Complaint Helper both slip past day 15 → cut Complaint Helper to view-only (mock it in the demo video).
If deployment slips past day 17 → submit with the local demo video and a "deployment coming" note.

**Never cut**: Contract Reader (anchor), one working Rights Guide flow, one chatbot session in Bengali.

---

## 11. Non-goals

Explicit list of what Sreshtha does **not** do, v1 or ever:

- **Legal advice.** We inform; we don't advise. Every module carries the disclaimer.
- **Filing complaints on the worker's behalf.** We draft; the worker submits.
- **Guaranteeing benefit disbursement.** We surface eligibility; the state processes claims.
- **Mediating between worker and platform.** We route complaints to the right authority; we don't play arbitrator.
- **Case law.** Statutes and schemes only. Case law requires lawyer review that we don't have.
- **Union organising tooling.** No group messaging, no protest coordination in v1 (v2 candidate).
- **Payment / earnings tracking.** Not our niche.
- **Job discovery.** Not our niche.
- **Contract drafting or negotiation.** We read, we don't write contracts.

---

## 12. Risks + mitigations + submission strategy

### 12.1 Product risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Translation quality in Bengali is worse than expected | Medium | High | Human review of top 5 fact cards; Sarvam provides best-in-class Indic; fall back to English + audio if a card is unclear |
| OCR fails on low-quality contract photos | High | High | Provide 3 pre-loaded samples so demo doesn't depend on live OCR; add "try a clearer photo" fallback |
| RAG recall is poor with only 15 fact cards | Medium | Medium | Fall back to LLM with "here's my best understanding" disclaimer; log misses as fact card candidates |
| Voice input latency too high on 3G | Medium | Medium | Ship without voice-first for slow networks; text always works |
| Legal advice creep in chatbot outputs | Medium | High | Deterministic Stage 2 rule: any response mentioning "you should sue" / "you are entitled to" without citation gets rewritten |

### 12.2 Submission risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gen AI Academy APAC registration is closed / paid / delayed | Medium | High | Register immediately Day 1. Have backup plan of Anthropic-based submission for another campaign. |
| Cloud Run outage day-of | Low | High | Have local build + demo video as backup; walkthrough deck if needed |
| Solo capacity — 20 days is tight | High | Medium | Slippage protocol above; anchor module non-negotiable; other modules degradable to functional-shell |
| Reviewer expects mobile app not web | Medium | Medium | Web is explicitly Meet the Builders scope; blog post frames "web-first, mobile PWA in v2" |

### 12.3 Submission narrative

For the blog post + video, the narrative arc:

1. **The problem** — 7.7 crore workers, no product exists. Show the Bengali migrant driver as the human face.
2. **The insight** — every gig platform is English/Hindi-only. This is not a product problem, it's a market gap.
3. **The build** — five integrated modules on a shell already in production. Contract Reader is the anchor.
4. **The tech** — Gemini + Sarvam split, retrieval-first chatbot, deterministic decisions.
5. **The demo** — Contract Reader Hindi flow (Rahul), chatbot Bengali flow (Sabina), Complaint Helper Tamil flow (Muthu).
6. **What's next** — B2B2C SaaS, PWA, union partnerships.

### 12.4 What we're not saying

- Not claiming legal accuracy of every output
- Not promising union endorsement (working on it)
- Not implying platform partnerships (soliciting them)
- Not stating specific complaint success rates (we don't have data yet)

---

## Appendix A — Research sources

- NITI Aayog, *India's Booming Gig and Platform Economy* (2022) — 7.7 crore workers today, 23.5 crore by 2030
- Fairwork India Annual Report 2024 — grading platforms on five principles
- IFAT (Indian Federation of App-based Transport Workers) surveys 2023-24 — hours, earnings, contract awareness
- Ola Mobility Institute *Working Conditions of Delivery Workers* 2023 — heat exhaustion, hours
- Ministry of Labour and Employment, Code on Social Security 2020, Rules 2024
- Government of Karnataka, Platform-Based Gig Workers (Social Security and Welfare) Ordinance 2025
- Government of Rajasthan, Platform-Based Gig Workers (Registration and Welfare) Act 2023
- e-Shram portal data (as of Q2 2024) — 30+ crore registrations
- India Labourline (1800-419-1550) — national labour helpline

## Appendix B — Competitive scan

Detailed in section 2.4. No direct competitor exists. Closest analogues:

- **Fairwork India** — advocacy/research vehicle, not a product
- **Namma Yatri** — alternative ride booking (Bangalore autos), single-city/single-modality
- **Kaam.com, Apna** — job discovery
- **State welfare board portals** — registration only, no discovery layer
- **Union WhatsApp groups** — peer support, no scale/persistence/language coverage

## Appendix C — Prior art in this codebase

- **QuickBites Support Bot** — the substrate: Cardinal pipeline, Stage 2 rules, response library, multi-provider LLM, admin panel, tenant config. Being retargeted for gig-worker domain.
- **thought-translate** — three-stage translation reasoning (Understand → Research → Synthesise). Being ported into Contract Reader.

## Appendix D — Open questions (to resolve during build)

1. Domain name — `sreshtha.app`? `sreshtha.in`? Register on Day 1 if available.
2. Logo — commission or hand-crafted? Day 2 decision.
3. OTP provider — MSG91 or Twilio? Day 1 decision (affects auth timing).
4. Video hosting — YouTube (unlisted) or Vimeo? Day 18.
5. Blog platform — Medium or personal? Day 19.
6. GitHub repo — public or private for submission? Public strongly preferred by campaign.

---

*End of PRD v0.1.*
