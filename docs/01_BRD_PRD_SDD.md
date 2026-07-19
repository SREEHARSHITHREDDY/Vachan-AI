# VachanAI
## Agentic AI Commitment & Relationship Intelligence Engine
### Combined Business Requirements, Product Requirements, and Solution Design Document

---

# PART 1: BUSINESS REQUIREMENTS DOCUMENT (BRD)

## 1.1 Purpose

This document defines the business rationale, objectives, scope, and success criteria for VachanAI — an agentic AI system that tracks commitments made in professional/academic communication and scores the health of important relationships over time. It exists to guide the semester-project build and to serve as the foundation for a phased commercial product.

## 1.2 Business Problem

Professionals, students, and executives make dozens of implicit commitments weekly across email, chat, and meetings, with no systematic way to track them. This results in missed deadlines, damaged professional relationships, and silently lost opportunities (a recruiter or investor follow-up that quietly dies). No current tool treats a promise as a trackable object with a lifecycle, or scores relationship decay as a standalone signal — existing AI assistants (Lindy, Sintra, Catch, Superhuman, Missive) triage by urgency/topic and focus on drafting/sending, not on promise-keeping or relationship health.

## 1.3 Business Objectives

1. Validate a defensible, patentable core technology (commitment lifecycle detection + relationship decay scoring) through a working prototype.
2. Establish a beachhead user base (students) at near-zero customer acquisition cost using existing campus distribution channels.
3. Build toward a phased, multi-tier SaaS revenue model that scales from free/freemium to enterprise contracts.
4. Produce a patent-ready technical/IP package alongside the product build.

## 1.4 Stakeholders

| Stakeholder | Interest |
|---|---|
| Founder/Developer | Builds the product, owns IP, drives roadmap |
| Academic mentor/supervisor | Evaluates semester deliverable, provides technical/academic guidance |
| Industry expert reviewers | Validate market fit and technical assumptions |
| Phase 1 users (students) | Early adopters, feedback source, testimonials |
| Phase 2 users (professionals) | First paying customers |
| Phase 3 users (CXOs/enterprise) | Long-term revenue scale target |
| Future patent attorney | Files and prosecutes IP protection |

## 1.5 Scope

**In scope (Phase 1 / semester deliverable):**
- Commitment extraction from Gmail and Slack
- Commitment lifecycle tracking
- Relationship decay scoring
- Calendar/reminder suggestion layer (confirmation-gated)
- Daily/weekly digest
- Student-mode taxonomy only

**Out of scope (deferred to later phases):**
- LinkedIn and WhatsApp integration (ToS/cost blockers)
- Auto-send/auto-reply functionality
- Multi-agent architecture (Recruitment Agent, Investor Relations Agent, etc.)
- Enterprise security/compliance features (SOC 2, RBAC, audit logs)
- Executive/professional-mode taxonomies (previewed only, not fully built)

## 1.6 Business Requirements

| ID | Requirement | Priority |
|---|---|---|
| BR-1 | System must extract commitments from at least two communication channels (email, chat) | High |
| BR-2 | System must not send or write anything without explicit user confirmation | High |
| BR-3 | System must be usable by a non-technical student user without setup friction beyond OAuth | High |
| BR-4 | System must produce a defensible technical description suitable for patent filing | Medium |
| BR-5 | System architecture must support persona reconfiguration without core engine rebuild | Medium |
| BR-6 | System must operate within free-tier API limits for Phase 1 (cost constraint) | High |

## 1.7 Success Metrics (Business Level)

- Number of active student pilot users (target: 15–25 for semester validation)
- Commitment extraction precision/recall against a labeled test set (target: >80% precision)
- Qualitative validation feedback from at least 1 industry expert and 1 academic mentor
- A complete, dated technical documentation package ready for patent attorney review

## 1.8 Assumptions & Constraints

- Assumes Gmail/Slack API access is sufficient for Phase 1 (no LinkedIn/WhatsApp dependency)
- Assumes student pilot users are willing to grant OAuth access to personal email/chat for testing
- Constrained by single-developer bandwidth and one-semester timeline
- Constrained by free-tier LLM API budget

## 1.9 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Low pilot user recruitment | Delays validation | Use existing campus roles (Dean Fellow, Student Ambassador) for distribution |
| LLM extraction accuracy too low | Undermines core value prop | Budget time for prompt iteration + labeled test set evaluation |
| Competitive overlap discovered late | Weakens patent/differentiation story | Conduct patent-landscape/prior-art search before filing anything |
| Conflict of interest with Nebulytix internship | Legal/professional risk | Confirm no shared resources/code before any public pitch or filing |

---

# PART 2: PRODUCT REQUIREMENTS DOCUMENT (PRD)

## 2.1 Product Vision

VachanAI is an agentic AI system that helps students, professionals, and executives keep every promise they make and never let an important relationship go cold — starting on campus and scaling into the workplace and boardroom as the same user's career grows.

## 2.2 Target Users & Personas (Phased)

| Phase | Persona | Key Needs |
|---|---|---|
| 1 | Student | Track assignment deadlines, group-project promises, recruiter/professor follow-ups |
| 2 | Professional | Track client/sales follow-ups, deliverable deadlines, networking follow-through |
| 3 | Executive | Track board/investor follow-ups, strategic partnership commitments |

## 2.3 User Stories (Phase 1 — Student Mode)

- As a student, I want the system to automatically detect when I've promised to do something in an email or Slack message, so I don't have to manually log it.
- As a student, I want to see which of my promises are at risk of being broken, so I can prioritize my day.
- As a student, I want to know if I've gone quiet with an important contact (a recruiter or professor), so I can follow up before it's too late.
- As a student, I want the system to suggest a calendar reminder for a deadline it detected, but only add it after I confirm.
- As a student, I want a daily summary so I don't have to check multiple tools separately.

## 2.4 Functional Requirements

| ID | Requirement | Description |
|---|---|---|
| FR-1 | Commitment Extraction | Parse email/Slack messages; classify segments as commitments (made-by-me, made-to-me, conditional, vague) |
| FR-2 | Lifecycle State Tracking | Maintain state per commitment: pending → approaching-deadline → at-risk → fulfilled/broken |
| FR-3 | Auto-Resolution Detection | Cross-reference new messages against open commitments to auto-detect fulfillment |
| FR-4 | Relationship Scoring | Compute per-contact score from response latency, frequency, sentiment trends, and role weight |
| FR-5 | Decay Alerting | Trigger an alert when a relationship score crosses a defined decay threshold |
| FR-6 | Calendar Suggestion | Propose calendar event/reminder for commitments with inferred deadlines |
| FR-7 | Confirmation Gate | Require explicit one-click user confirmation before any calendar write |
| FR-8 | Escalating Reminders | Adjust reminder urgency based on lifecycle state and proximity to deadline |
| FR-9 | Daily Digest | Generate a read-only summary of at-risk commitments, decaying relationships, and upcoming deadlines |
| FR-10 | Feedback Loop | Allow user to confirm/correct flagged commitments; feed corrections back into extraction accuracy over time |
| FR-11 | Persona Taxonomy Config | Support swapping the commitment/contact taxonomy without retraining the core engine |

## 2.5 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | No message content is sent or written externally without explicit user action |
| NFR-2 | System must operate within free/low-cost API tiers for Phase 1 |
| NFR-3 | Extraction latency should not exceed a few seconds per message batch for usable digest generation |
| NFR-4 | User data (messages, scores) stored securely; no third-party data sharing |
| NFR-5 | System should be usable by a non-technical user with only OAuth-level setup |

## 2.6 Out of Scope (Phase 1)

- LinkedIn/WhatsApp integrations
- Auto-send or auto-reply capability
- Full multi-agent architecture
- Enterprise security/compliance (SOC 2, RBAC, audit logs) — deferred to Phase 3
- Executive-mode full feature set (preview/mockup only)

## 2.7 Release Plan

| Release | Scope |
|---|---|
| Phase 1 (Semester) | Student Mode: extraction, lifecycle tracking, decay scoring, calendar action layer, digest |
| Phase 2 (Post-semester) | Professional Mode: LinkedIn integration (via approved API), CRM-style tagging, subscription billing |
| Phase 3 (Scale) | Executive Mode: SOC 2, RBAC, audit logs, enterprise SSO, multi-agent expansion |

## 2.8 Success Metrics (Product Level)

- Commitment extraction precision/recall on labeled test data
- Percentage of proposed calendar actions confirmed (not dismissed) by users
- Reduction in self-reported "missed commitments" among pilot users (survey-based)
- User retention across a multi-week pilot period

---

# PART 3: SOLUTION DESIGN DOCUMENT (SDD)

## 3.1 Architecture Overview

VachanAI's Phase 1 architecture is a single-orchestrator agentic system (not multi-agent) with four core processing modules operating over data pulled from Gmail and Slack, backed by a relational database and a local vector store.

```
                     ┌─────────────────────────┐
                     │     User (OAuth)         │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │   Ingestion Layer        │
                     │  (Gmail API, Slack API)  │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │  Orchestrating Agent     │
                     │  (LLM-based)             │
                     └─────┬───────────┬───────┘
                           │           │
         ┌─────────────────▼───┐   ┌───▼─────────────────────┐
         │ Commitment Extraction │   │ Relationship Scoring   │
         │ + Lifecycle Tracker   │   │ Engine                 │
         └─────────┬────────────┘   └───────────┬────────────┘
                   │                             │
         ┌─────────▼─────────────────────────────▼────────────┐
         │              PostgreSQL (structured records)         │
         │              Chroma (vector store, semantic context) │
         └─────────┬─────────────────────────────┬─────────────┘
                   │                             │
         ┌─────────▼────────────┐     ┌──────────▼────────────┐
         │ Calendar Action Layer │     │ Digest Generator       │
         │ (Google Calendar API, │     │ (Daily/Weekly Summary) │
         │  confirmation-gated)  │     └────────────────────────┘
         └───────────────────────┘
```

## 3.2 Component Descriptions

**Ingestion Layer** — Pulls messages via Gmail and Slack APIs on a scheduled/polling basis (or webhook where supported), normalizes into a common message schema (sender, recipient, timestamp, channel, body).

**Orchestrating Agent** — A single LLM-driven controller that routes each incoming message batch to the extraction and scoring modules, and coordinates the confirmation-gated action layer. Kept as a single agent for Phase 1 to reduce complexity; designed so it can be decomposed into specialized sub-agents in Phase 3 without a full rebuild.

**Commitment Extraction + Lifecycle Tracker** — Classifies message segments as commitments and assigns initial state. On each new message batch, cross-references existing open commitments to detect fulfillment/breakage (the core patentable mechanism — see Section 3.6).

**Relationship Scoring Engine** — Computes and updates per-contact scores on a rolling basis using response-latency trend, frequency trend, and sentiment trend (via lightweight sentiment classification), weighted by a configurable role-importance value.

**Calendar Action Layer** — Generates a proposed calendar event/reminder object when a commitment has an inferred deadline; holds it in a "proposed" state until the user confirms via the dashboard, at which point it's written via the Google Calendar API.

**Digest Generator** — Runs on a schedule (daily/weekly) to compile a read-only summary from the current state of commitments and relationship scores.

## 3.3 Data Model (Core Entities)

| Entity | Key Fields |
|---|---|
| User | user_id, oauth_tokens, persona_mode, created_at |
| Contact | contact_id, user_id (FK), name, role_tag, importance_weight |
| Message | message_id, user_id (FK), contact_id (FK), channel, timestamp, body_ref, direction |
| Commitment | commitment_id, user_id (FK), contact_id (FK), source_message_id (FK), type (made-by-me/made-to-me/conditional/vague), state, inferred_deadline, created_at, resolved_at |
| RelationshipScore | score_id, contact_id (FK), latency_trend, frequency_trend, sentiment_trend, composite_score, computed_at |
| CalendarAction | action_id, commitment_id (FK), proposed_at, status (proposed/confirmed/dismissed), calendar_event_id |
| FeedbackCorrection | correction_id, commitment_id (FK), user_verdict (confirmed/rejected), corrected_at |

## 3.4 Technology Stack

| Layer | Choice |
|---|---|
| LLM | Claude or GPT API |
| Backend | Python + FastAPI |
| Orchestration | Single-agent controller (LangChain or lightweight custom) |
| Database | PostgreSQL (structured), Chroma (vector/semantic) |
| Integrations | Gmail API, Slack API, Google Calendar API |
| Frontend | React (glassmorphism/Framer Motion design language) |

## 3.5 Security & Privacy Design (Phase 1 Level)

- OAuth-based access only; no credential storage beyond tokens
- No message content forwarded to third parties beyond the LLM API call itself
- All calendar writes gated behind explicit user confirmation (no autonomous writes)
- Data scoped per-user; no cross-user data sharing
- Full enterprise-grade controls (SOC 2, RBAC, audit logging) deliberately deferred to Phase 3 where the buyer and risk profile justify the investment

## 3.6 Patentable Technical Mechanism (Reference)

The core technical novelty sits in the **closed-loop cross-referencing mechanism**: when a new message arrives, the system checks it against all currently open commitments (not just the thread it belongs to) and updates commitment state based on independent evidence of fulfillment — rather than requiring the user to manually resolve each item. Combined with the **adaptive feedback loop** (Section 2.4, FR-10), where user corrections adjust future extraction behavior, this forms the primary defensible IP claim for the system. (Full patentability analysis maintained separately.)

## 3.7 Scalability Considerations

- Phase 1: single-tenant, low-volume, free-tier API usage sufficient
- Phase 2: introduce queued/batched processing for higher message volume as professional users generate more data
- Phase 3: move to production-grade vector DB (Pinecone/Weaviate), introduce proper multi-agent decomposition, and add enterprise security layer

---

*This combined document is intended as a living reference — update the BRD as business priorities shift, the PRD as features are scoped per release, and the SDD as the actual implementation solidifies.*
