# VachanAI — Phase 5: Software Architecture
### Deep Architecture Document (Component, Sequence, Deployment, Monolith vs. Microservices)

---

## 5.1 Architectural Approach & Reasoning

Before any diagrams: the guiding constraint for Phase 1 is that this is a solo-built, one-semester system that needs to be demoable, testable, and extensible — not yet a system built for scale. Every decision below is made against that constraint first, with an explicit note on how it changes at Phase 2/3 scale.

---

## 5.2 High-Level Architecture (Layered View)

VachanAI is structured in five layers. Each layer has one job, and layers only talk to the layer directly above/below them — this is what makes it possible to later split any layer into its own service without a rewrite.

| Layer | Responsibility |
|---|---|
| **Presentation Layer** | React dashboard — commitment list, relationship scores, digest view, calendar-action confirmation UI |
| **API Layer** | FastAPI application — exposes REST endpoints, handles auth, request validation, routes to services |
| **Service Layer** | The core logic: Extraction Service, Lifecycle Service, Scoring Service, Action Service, Digest Service, Feedback Service |
| **Data Layer** | PostgreSQL (structured state) + Chroma (semantic/vector context) |
| **Integration Layer** | Gmail API, Slack API, Google Calendar API, LLM API (Claude/GPT) |

**Why layered instead of something looser:** a layered architecture is the simplest structure that still gives you a clean seam to cut along later — when Phase 3 needs to pull the Scoring Service into its own deployable unit, it's already isolated behind a clear interface instead of tangled into a single script.

---

## 5.3 Component Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                          │
│  React Dashboard: Commitment View | Relationship View | Digest    │
│                  | Calendar Confirmation UI                        │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │ HTTPS / REST (JSON)
┌───────────────────────────────▼─────────────────────────────────────┐
│                            API LAYER                                │
│   FastAPI App                                                       │
│   ├─ Auth Router (OAuth token handling)                             │
│   ├─ Commitments Router                                             │
│   ├─ Contacts/Relationships Router                                  │
│   ├─ Actions Router (calendar confirm/dismiss)                      │
│   └─ Digest Router                                                  │
└───────┬─────────┬─────────┬─────────┬─────────┬───────────────────┘
        │         │         │         │         │
┌───────▼──┐ ┌────▼─────┐ ┌─▼───────┐ ┌▼────────┐ ┌▼─────────────┐
│Extraction│ │ Lifecycle│ │ Scoring │ │ Action  │ │ Digest        │
│ Service  │ │ Service  │ │ Service │ │ Service │ │ Service       │
└───────┬──┘ └────┬─────┘ └─┬───────┘ └┬────────┘ └┬─────────────┘
        │         │         │          │           │
        └─────────┴────┬────┴──────────┴───────────┘
                        │
          ┌─────────────▼──────────────┐
          │        DATA LAYER            │
          │  PostgreSQL (structured)     │
          │  Chroma (semantic/vector)    │
          └─────────────┬──────────────┘
                        │
          ┌─────────────▼──────────────────────────────┐
          │           INTEGRATION LAYER                  │
          │  Gmail API │ Slack API │ Calendar API │ LLM  │
          └──────────────────────────────────────────────┘
```

**Component notes:**
- **Extraction Service** and **Lifecycle Service** are shown separately even though they share data, because they have different triggers: Extraction runs on new-message-arrival; Lifecycle runs on every message arrival (new or old context) to check for resolution of *existing* commitments. Keeping them as distinct services (even inside one deployable app for Phase 1) is what lets you scale or replace one without touching the other later.
- **Feedback Service** (from FR-10 in the PRD) is intentionally folded into the Extraction Service for Phase 1 rather than given its own box — it's a small enough responsibility (log correction, adjust few-shot examples/prompt weighting) that a separate service would be over-engineering at this stage.

---

## 5.4 Data Flow (Primary Scenarios)

### Scenario A: New message arrives → commitment extracted → digest updated

1. Ingestion polling job (or webhook, where supported) pulls new messages from Gmail/Slack via Integration Layer.
2. Message normalized into common schema, stored in PostgreSQL (`Message` table).
3. API Layer triggers Extraction Service on the new message.
4. Extraction Service calls the LLM API with the message + few-shot prompt context; returns classified commitment segments (if any).
5. New `Commitment` record created (state = `pending`) if a commitment was detected.
6. In parallel, Lifecycle Service checks the new message against all currently open commitments for this user (cross-referencing) — if it finds evidence of fulfillment, updates the matching commitment's state to `fulfilled`.
7. Scoring Service recalculates the relevant contact's relationship score using the new message's timestamp/sentiment.
8. Digest Service reads current state (on schedule) and compiles the next digest.

### Scenario B: Commitment has an inferred deadline → calendar action proposed → user confirms

1. When Extraction Service creates a commitment with an inferred deadline, it emits an event to the Action Service.
2. Action Service creates a `CalendarAction` record in state `proposed` (nothing written to the actual calendar yet).
3. Frontend displays the proposed action in the dashboard with confirm/dismiss controls.
4. User clicks confirm → API Layer calls Action Service → Action Service calls Google Calendar API to create the actual event → `CalendarAction.status` updated to `confirmed`, `calendar_event_id` stored.
5. If the user dismisses instead, `status` is set to `dismissed` and no external write ever occurs.

---

## 5.5 Sequence Diagram (Text): Commitment Lifecycle Auto-Resolution

This is the sequence behind your core patentable mechanism, so it's worth spelling out precisely.

```
User          Gmail/Slack API      API Layer      Lifecycle Service      PostgreSQL      LLM API
 │                  │                  │                  │                  │             │
 │  (new message arrives, unrelated thread)                                   │             │
 │                  │──message────────▶│                  │                  │             │
 │                  │                  │──normalize───────────────────────────▶ store Msg   │
 │                  │                  │──trigger────────▶│                  │             │
 │                  │                  │                  │──fetch open commitments────────▶│
 │                  │                  │                  │◀────list of open commitments────│
 │                  │                  │                  │──ask LLM: does this message──────▶│
 │                  │                  │                  │  resolve any of these commitments?│
 │                  │                  │                  │◀───classification result──────────│
 │                  │                  │                  │──update commitment state──────────▶│
 │                  │                  │                  │   (pending → fulfilled)            │
 │                  │                  │◀─confirmation────│                  │             │
 │  (dashboard reflects updated state on next load/poll)                                     │
```

**Design decision explained:** the Lifecycle Service asks the LLM specifically "does this message resolve any of these *N* open commitments," rather than re-running general extraction on every message against the whole commitment history — this keeps the check bounded (only open commitments for that user/contact, not the full history) and keeps latency and API cost predictable as commitment volume grows.

---

## 5.6 Sequence Diagram (Text): Calendar Action Confirmation

```
User          Frontend           API Layer        Action Service      Google Calendar API
 │                │                  │                  │                    │
 │  sees proposed action in dashboard│                  │                    │
 │──clicks "Confirm"───────────────▶│                  │                    │
 │                │──POST /actions/confirm────────────▶│                    │
 │                │                  │──create event───────────────────────▶│
 │                │                  │                  │◀──event_id─────────│
 │                │                  │◀─update status: confirmed──────────────
 │                │◀─success─────────│                  │                    │
 │◀─UI updates────│                  │                  │                    │
```

**Design decision explained:** the write to Google Calendar only happens after the explicit POST from a real user click — there is no code path where an event is created without this request originating from the frontend confirm button. This is deliberate, both for user trust and because it's the cleanest way to demonstrate the "confirmation-gated" claim if this ever supports a patent application.

---

## 5.7 Deployment Diagram (Text)

Phase 1 deployment target is intentionally minimal — free/low-cost tiers, single-region, no redundancy, since the goal is a working demoable system, not production infrastructure.

```
┌─────────────────────┐
│   Student's Browser   │
└──────────┬───────────┘
           │ HTTPS
┌──────────▼───────────┐
│  Frontend Hosting      │   (Vercel or Netlify free tier)
│  React static build    │
└──────────┬───────────┘
           │ HTTPS (API calls)
┌──────────▼───────────┐
│  Backend Hosting        │   (Render or Railway free/hobby tier)
│  FastAPI app             │
└──────┬───────────┬─────┘
       │           │
┌──────▼─────┐ ┌───▼──────────┐
│ PostgreSQL   │ │ Chroma        │   (Managed Postgres free tier;
│ (managed)    │ │ (local/disk)  │    Chroma run alongside backend,
└──────────────┘ └───────────────┘    not a separate managed service yet)
       │
┌──────▼─────────────────────────────────────┐
│           External APIs (called from backend)│
│  Gmail API │ Slack API │ Calendar API │ LLM API│
└────────────────────────────────────────────────┘
```

**Design decision explained:** Chroma runs as an embedded/local process alongside the backend rather than as its own managed service — this avoids a third hosting bill and third point of failure for a semester project where message volume is small enough that a local vector store is entirely sufficient. This is explicitly called out as something that changes at Phase 2/3 scale (see 5.9).

---

## 5.8 Monolith vs. Microservices — Explicit Analysis

| Factor | Monolith (chosen for Phase 1) | Microservices |
|---|---|---|
| Team size | Solo developer — one deployable unit is far easier to build, debug, and demo | Needs a team to own separate services; overkill for one person |
| Message volume | Low (single-user pilot testing) — no service needs independent scaling yet | Justified only when one component (e.g., extraction) needs to scale independently of others |
| Deployment complexity | One app to deploy, one place to check logs | Multiple deployments, service discovery, inter-service networking — unnecessary complexity now |
| Latency | In-process calls between services (Extraction → Lifecycle → Scoring) are fast and simple | Network calls between services add latency and failure modes not worth taking on yet |
| Patent/demo needs | A single, coherent, easy-to-explain system is actually *better* for demoing the closed-loop mechanism to a mentor/patent attorney | Splitting the loop across services early would make the core mechanism harder to explain, not easier |

**Decision: Monolith for Phase 1.** The layered structure inside the monolith (Section 5.2) is what preserves the *option* to split into microservices later without a rewrite — this is often called a "modular monolith," and it's the right choice here specifically because the internal boundaries (Extraction Service, Lifecycle Service, Scoring Service, etc.) are already cleanly separated by interface, just not by network boundary yet.

---

## 5.9 Evolution Path: When Each Piece Actually Needs to Split Out

| Trigger | What Splits Out | Why |
|---|---|---|
| Phase 2: Message volume grows across paying professional users | Extraction Service → its own worker process/queue (e.g., Celery + Redis) | Extraction is the most LLM-call-heavy and latency-sensitive piece; isolating it lets you scale workers independently of the API |
| Phase 2: Chroma outgrows local/disk storage | Chroma → managed vector DB (Pinecone/Weaviate) | Needed once semantic search volume and concurrent users exceed what an embedded instance handles reliably |
| Phase 3: Enterprise customers require uptime guarantees | API Layer → containerized, multi-instance deployment behind a load balancer | Single-instance hosting is no longer acceptable at enterprise SLA expectations |
| Phase 3: True multi-agent architecture (Recruitment Agent, Investor Relations Agent, etc.) | Service Layer → each specialized agent as its own service | At that point, different agents may have genuinely different scaling/latency/cost profiles worth isolating |

**The key point:** none of this is guessed at randomly — each split is tied to a specific, checkable trigger (volume, SLA requirement, feature scope), so you're not over-building infrastructure for a stage you haven't reached yet, which is exactly the kind of premature complexity the "never generate unnecessary code" principle is meant to prevent.

---

## 5.10 Summary of Design Decisions in This Phase

| Decision | Chosen Approach | Rejected Alternative | Why |
|---|---|---|---|
| Overall architecture style | Modular monolith | Microservices from day one | Team size (1) and message volume don't justify network-boundary complexity yet |
| Vector store hosting | Embedded Chroma | Managed Pinecone/Weaviate | Free, sufficient for pilot-scale data, avoids third hosting dependency |
| Lifecycle resolution check | Bounded check against open commitments only | Re-running full extraction against entire history | Keeps latency/cost predictable as commitment volume grows |
| Calendar writes | Confirmation-gated, user-triggered only | Autonomous writes on detection | Preserves user trust and the patentable "confirmation-gated" claim |
| Feedback loop | Folded into Extraction Service | Standalone Feedback Service | Too small a responsibility to justify its own service at this stage |

---

*Next phase per the framework: Phase 6 — Technology Stack (deeper justification per component) or Phase 7 — Project Structure (actual folder scaffolding), whichever you'd like to tackle next.*
