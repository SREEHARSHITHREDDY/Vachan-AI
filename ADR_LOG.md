# VachanAI — Architecture Decision Record Log

Per the Reconciliation Addendum (Item 1), this log complements the inline
"design decision explained" prose already in each doc — it's the
single-place, dated, numbered trail useful both for onboarding and as
patent-documentation evidence. New decisions get appended here as they're
made; existing decisions were backfilled below.

---

### ADR-001: Modular Monolith over Microservices (Phase 1)
**Context:** Choosing overall system architecture style.
**Decision:** Single deployable modular monolith, with clean internal
service boundaries (Extraction/Lifecycle/Scoring/Action/Digest).
**Alternatives considered:** Microservices from day one.
**Consequences:** Faster to build/debug/demo solo; internal boundaries
preserve the option to split services out later without a rewrite.
*(Source: Phase 5 Architecture doc, Section 5.8)*

---

### ADR-002: REST over GraphQL/WebSockets (Phase 1)
**Context:** API style selection.
**Decision:** REST, versioned at `/api/v1/`.
**Alternatives considered:** GraphQL (flexible querying), WebSockets (real-time push).
**Consequences:** Faster to build for one known client (own dashboard);
WebSocket push and GraphQL remain named Phase 2/3 additions if triggers are met.
*(Source: API Design doc, Section 5.1)*

---

### ADR-003: Embedded Chroma over Managed Vector DB (Phase 1)
**Context:** Vector store selection for semantic context retrieval.
**Decision:** Embedded/local Chroma instance alongside the backend.
**Alternatives considered:** Pinecone, Weaviate.
**Consequences:** No extra hosting cost/dependency at pilot scale;
migration path to managed vector DB defined for Phase 2/3.
*(Source: Database Design doc, Section 4.1; Phase 5 SDD, Section 5.7)*

---

### ADR-004: Few-Shot Prompting over Fine-Tuning
**Context:** How the commitment extraction model is implemented.
**Decision:** Few-shot prompting with ~10-15 labeled examples, no custom-trained model.
**Alternatives considered:** Fine-tuned classifier; rule-based/regex extraction.
**Consequences:** No large labeled dataset required for Phase 1; revisit
fine-tuning once real usage data accumulates (Phase 2/3).
*(Source: AI Architecture doc, Section 7.2)*

---

### ADR-005: Single Orchestrating Agent over Multi-Agent Architecture
**Context:** Agent architecture for Phase 1.
**Decision:** One orchestrator handling extraction, lifecycle, and scoring calls.
**Alternatives considered:** Specialized multi-agent system (Recruitment Agent, Investor Relations Agent, etc.).
**Consequences:** Simpler, more predictable, easier to demo/explain (including for patent purposes);
multi-agent expansion deferred to Phase 3.
*(Source: AI Architecture doc, Section 7.8; Phase 5 SDD, Section 5.2)*

---

### ADR-006: Confirmation-Gated Calendar Actions (No Autonomous Writes)
**Context:** How detected commitments translate into calendar events.
**Decision:** System only ever proposes a calendar action; a real Calendar API
write happens only after explicit one-click user confirmation.
**Alternatives considered:** Autonomous write on detection.
**Consequences:** Preserves user trust; also functions as the primary
mitigation for the prompt-injection risk described in AI Architecture 7.9 —
one decision serving two purposes.
*(Source: API Design doc, Section 5.4; AI Architecture doc, Section 7.9)*

---

### ADR-007: Cursor-Based Pagination over Offset-Based
**Context:** Pagination strategy for list endpoints.
**Decision:** Cursor-based (`?cursor=<token>&limit=20`).
**Consequences:** Avoids the "page 2 shifts as new rows insert" problem; cheaper on Postgres as tables grow.
*(Source: API Design doc, Section 5.5)*

---

### ADR-008: 404 (not 403) on Cross-User Resource Access
**Context:** Error response when a user requests another user's resource.
**Decision:** Return 404 Not Found, not 403 Forbidden.
**Consequences:** Avoids confirming to an attacker that a given resource ID exists at all.
*(Source: API Design doc, Section 5.6)*

---

### ADR-009: Natural Idempotency over Formal Idempotency-Key Header (Phase 1)
**Context:** Preventing duplicate processing on critical POST operations.
**Decision:** Rely on status-check-based natural idempotency
(e.g., confirming an already-confirmed action returns 409, not a duplicate write).
**Alternatives considered:** Formal `Idempotency-Key` header support.
**Consequences:** Sufficient for Phase 1 (no payment/high-stakes writes yet);
formal header support triggered by Phase 2 payment features.
*(Source: API Design doc, Section 5.7; Reconciliation Addendum, Item 3)*

---

### ADR-010: Response Envelope Standardized with `success` Boolean
**Context:** Reconciling two slightly different response shapes used across docs.
**Decision:** `{"success": bool, "data"|"error": ...}`, with `meta` retained for pagination counts.
**Consequences:** Single consistent contract across all endpoints.
*(Source: Reconciliation Addendum, Item 4)*

---

### ADR-011: snake_case Filenames for Python Backend (Override of Generalized Framework)
**Context:** Module 08 of the generalized framework mandates PascalCase filenames (JS/TS convention).
**Decision:** Python backend uses snake_case filenames (`extraction_service.py`),
PascalCase for class names inside; frontend keeps PascalCase filenames for React components.
**Consequences:** Matches Python idiom rather than blindly applying a JS-centric rule.
*(Source: Reconciliation Addendum, Item 2)*

---

### ADR-012: Scoped Soft-Delete (Not Full Audit Logging) for Phase 1
**Context:** Module 04 mandates full audit logging + soft-delete on every table.
**Decision:** Soft-delete added only to `commitments` and `contacts`
(`is_deleted`, `deleted_at`); no before/after audit trail beyond the
existing commitment lifecycle state tracking; `messages` keeps hard delete.
**Consequences:** Preserves relationship-scoring history when a contact is
hidden, without building full audit infrastructure prematurely.
*(Source: Reconciliation Addendum, Item 5)*

---

### ADR-013: 60% Coverage Target, Scoped to Core Services Only
**Context:** Module 09 sets an 80% unit test coverage standard project-wide.
**Decision:** 60% coverage target applied only to Extraction, Lifecycle,
and Scoring services — not UI glue code or simple CRUD routes.
**Consequences:** Focuses solo-developer testing effort where correctness
actually matters for the product's core value and patent claim.
*(Source: Reconciliation Addendum, Item 6)*

---

### ADR-014: Trade Secret vs. Patent Disclosure Split
**Context:** Patents require public disclosure of the invention.
**Decision:** The closed-loop lifecycle detection *mechanism* is patentable
subject matter; the exact few-shot prompt wording and any tuned threshold
values (decay score cutoffs, confidence thresholds) are kept as trade
secrets, not disclosed in any patent specification.
**Consequences:** Method is protectable via patent; implementation details
that improve with iteration stay confidential.
*(Source: Reconciliation Addendum, Item 17)*

---

### ADR-015: Consolidated Documentation over 18 Separate Files
**Context:** Module 13 of the generalized framework specifies 18 discrete documentation files.
**Decision:** Keep documentation consolidated (combined BRD/PRD/SDD, one
Execution Plan, per-module docs) for Phase 1; all 18 topics are covered,
just not physically split.
**Consequences:** Less cross-linking overhead for a single-developer,
small-audience project; revisit if a team or open-source audience emerges.
*(Source: Reconciliation Addendum, Item 15)*

---

### ADR-016: Students-First Phased Persona Rollout
**Context:** Whether to build for students, professionals, and executives simultaneously.
**Decision:** Build and validate Student Mode first; Professional and
Executive modes are sequenced Phase 2/3 additions on the same underlying
engine with a swappable taxonomy layer.
**Consequences:** Avoids diluted ICP; gives a concrete, self-testable
beachhead market with near-zero cold-start data cost.
*(Source: Mentor Review Brief; BRD Section 8)*
