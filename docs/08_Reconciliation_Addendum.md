# VachanAI — Reconciliation & Consistency Addendum
### v1.0 — Resolves all inconsistencies flagged across Modules 00–18 vs. the actual VachanAI Phase 1 spec

This document is the authoritative tie-breaker. Where it conflicts with an earlier VachanAI document (BRD/PRD/SDD, Database Design, API Design, UI/UX, AI Architecture), **this addendum wins.** Nothing here requires rebuilding what's already written — each item below states the final decision and which existing doc/section it amends.

---

## 1. Architecture Decision Records (ADR format)

**Conflict:** Modules 03 and 13 require formal discrete ADR entries; our docs so far explain decisions inline ("Design decision explained:" prose).

**Resolution: Both, not either/or.** Keep inline prose explanations in each doc (better for reading in context) AND maintain one running lightweight ADR log — a simple numbered list (Decision / Context / Alternatives / Consequences, 3-4 lines each) — as a single appendix file. Every major decision already made across our docs gets a one-line backfilled entry. This log is also useful patent-documentation evidence (dated reasoning trail), so it serves two purposes at once.

*Action: maintain `ADR_LOG.md` going forward; backfill the ~15 major decisions already made (monolith vs. microservices, REST vs. GraphQL, embedded vs. managed vector store, etc.) as ADR-001 through ADR-015 next.*

---

## 2. File Naming Convention

**Conflict:** Module 08 mandates PascalCase per file (JS/TS convention); VachanAI's backend is Python/FastAPI, where idiomatic convention is snake_case filenames.

**Resolution:** Override Module 08 for the backend. **Python/FastAPI backend: snake_case filenames** (`commitment_service.py`, `lifecycle_tracker.py`), PascalCase for class names inside them (`CommitmentService`). **React frontend: PascalCase filenames** for components (`CommitmentCard.jsx`), camelCase for hooks/utilities — this part of Module 08 already matches frontend convention correctly. The generalized module's blanket rule only breaks for the Python side.

---

## 3. Idempotency-Key Header

**Conflict:** Module 05 mandates formal `Idempotency-Key` header support; our API doc deferred this, relying on natural idempotency via status checks.

**Resolution: Keep the deferral, but make it explicit rather than silent.** Phase 1 has no payment or other high-stakes duplicate-sensitive writes — natural idempotency (checking `CalendarAction.status` before acting) covers the actual risk surface. Formal `Idempotency-Key` headers remain a named Phase 2 addition, triggered specifically when payment processing or other high-stakes writes are introduced (unchanged from the original API doc's evolution table).

---

## 4. API Response Envelope

**Conflict:** Module 05 specifies `{"success": bool, "data"|"error": ...}`; our API doc used a bare `{"data": [...], "meta": {...}}` / `{"error": {...}}` shape without a `success` boolean.

**Resolution: Adopt Module 05's `success` boolean, merged with our existing `meta` field.**

Final standard shape:
```json
// Success
{ "success": true, "data": [...], "meta": {"count": 1} }

// Error
{ "success": false, "error": {"code": "...", "message": "...", "field": "..."} }
```
*Action: this supersedes the examples in the API Design doc (Section 5.4) — same endpoints, updated envelope.*

---

## 5. Audit Logging & Soft Delete

**Conflict:** Module 04 mandates audit logging (created_by/updated_by/deleted_by + before/after values) and soft-delete as standard practice on every table; our schema uses hard `ON DELETE CASCADE` with no soft-delete or audit trail.

**Resolution: Partial adoption, not full compliance — scoped to where it actually matters.**
- **Soft-delete added** to `commitments` and `contacts` only (`is_deleted`, `deleted_at`) — a user hiding a contact or commitment shouldn't destroy the relationship-scoring history that depended on it.
- **Full audit logging (before/after value tracking) is NOT added** for Phase 1 — this is genuinely premature for a single-user pilot with no compliance requirement yet. The `Commitment.state` transition history (already tracked via the lifecycle mechanism itself) serves as a lightweight, purpose-built substitute for the one place audit history actually matters.
- `messages` keeps hard delete via cascade — no business reason to soft-delete raw ingested messages independently of their parent user.

*Action: amends Database Design doc, Section 4.3 (`commitments`, `contacts` tables gain two columns each) and Section 4.7 (moves from "deferred" to "partially adopted, scoped").*

---

## 6. Test Coverage Targets

**Conflict:** Module 09 sets hard targets (Unit ≥80%, Integration ≥70%, API 100% critical); no targets exist in our Execution Plan.

**Resolution: Adopt a scoped-down Phase 1 target, not the full standard.** **60% unit test coverage, applied only to the three core services** (Extraction, Lifecycle Tracker, Scoring) — these are where correctness actually matters for the patent claim and the product's core value; exhaustively testing UI glue code and simple CRUD routes is not a good use of solo-developer time this semester. Module 09's 80%/70%/100% standard becomes the Phase 2/3 target once there's a team to sustain it.

---

## 7. Cross-Platform/Browser/OS Test Matrix

**Conflict:** Module 09 specifies a full matrix (4 browsers × 3 device classes × 5 OSes).

**Resolution: Scoped to Chrome + Safari, Desktop + Mobile web only** for Phase 1 — this covers the realistic device spread of a Woxsen student pilot group. Full matrix testing is explicitly deferred to a Phase 2+ distribution decision, not attempted now.

---

## 8. Deployment Environments & Strategy

**Conflict:** Module 10 assumes 4 full environments (Dev/Test/Staging/Prod) and offers Blue-Green/Canary as standard strategies.

**Resolution: Confirmed deferral, now explicit.** Phase 1 uses exactly **two environments: local Dev and a single Production deployment** — no Staging/Testing environment yet, since there's one developer and no team to coordinate around environment parity. Blue-Green/Canary remain named Phase 3 additions, already tied to the "enterprise SLA" trigger in the Phase 5 Architecture doc's evolution table — no change needed there, just confirming it stands.

---

## 9. Disaster Recovery Plan (RTO/RPO)

**Conflict:** Module 10 requires a formal DR plan as standard; our Database Design doc treated RTO/RPO as a Phase 3 trigger item only.

**Resolution: Write a minimal version now — this one is cheap enough not to skip.**

> **Phase 1 DR Plan:** If the Postgres database is lost or corrupted, restore from the managed hosting provider's automatic daily backup. Acceptable **RTO: ~24 hours, RPO: ~24 hours** for Phase 1 pilot stakes (losing up to a day of commitment/message data during a pilot is recoverable and non-catastrophic). No custom backup infrastructure is built — this relies entirely on the managed Postgres provider's built-in daily backup. Full DR planning (faster RTO/RPO, tested failover) remains a genuine Phase 3 item once real paying customers create real stakes.

---

## 10–12. GDPR, Incident Response, Trademark

**Resolution (per earlier decision): noted and carried forward, not addressed today.** No pilot user data is flowing yet and there's no public brand exposure yet — but all three get resolved before either of those changes:
- **GDPR-style handling** (data minimization, right-to-deletion) — resolve before any pilot volunteer's real inbox data is processed (i.e., before Execution Plan Week 9).
- **Lightweight incident response plan** (who's notified, immediate steps if OAuth tokens are compromised) — same trigger, before Week 9.
- **Trademark on "VachanAI"** — resolve before any public launch/demo beyond mentor and industry-expert review already done.

---

## 13. Performance Budget

**Conflict:** Module 12 sets targets (API <200ms, AI response <5s, memory <75%, CPU <70%) calibrated for a scaled service; VachanAI Phase 1 has no targets set and calls an LLM on the critical path, which routinely exceeds 200ms/5s.

**Resolution: Relaxed, LLM-aware targets for Phase 1:**

| Metric | Module 12 Standard | VachanAI Phase 1 Target |
|---|---|---|
| API response (non-AI endpoints) | <200ms | <300ms |
| AI-dependent response (extraction, lifecycle check) | N/A | <10 seconds |
| Database query | <100ms | <150ms |
| Memory/CPU | <75%/<70% | Not actively monitored — single-instance Phase 1 has no autoscaling to trigger off these anyway |

These are reference targets for manual sanity-checking, not enforced/alerted budgets — active performance monitoring infrastructure is a Phase 2+ addition once there's real concurrent load to monitor.

---

## 14. Load Testing — Module Overlap

**Conflict:** Load testing appears in both Module 09 (Testing & QA) and Module 12 (Performance Optimization).

**Resolution:** The *act* of running load tests belongs to Testing & QA (09); *tuning in response to* load test results belongs to Performance Optimization (12) — no actual overlap once split this way. **For Phase 1 specifically: skip formal load testing entirely.** A single-digit pilot user group creates no concurrency worth testing. This becomes a genuine Phase 2 activity once paid professional-tier users create real concurrent load worth measuring.

---

## 15. Documentation Structure (18 files vs. consolidated)

**Conflict:** Module 13 specifies 18 separate documentation files; VachanAI's actual documentation is consolidated (BRD/PRD/SDD combined, one Execution Plan, per-module docs like this one).

**Resolution: Keep the consolidated approach for Phase 1.** Splitting into 18 discrete files adds real overhead (cross-linking, staying in sync) with no benefit for the current audience (you, your mentor, one industry expert, eventually a patent attorney). **All 18 topics need to be covered somewhere — verified they are** — but physically splitting into 18 files is deferred until there's an actual team or open-source audience that benefits from that granularity.

---

## 16. Patentability Rescoring (Module 14's Weighted Scorecard Applied)

Applying Module 14's weighted formula (Novelty 25%, Inventive Step 20%, Technical Contribution 15%, Commercial Potential 15%, Scalability 10%, Market Demand 10%, Defensibility 5%) to the 6 patent points from the earlier Patentable Points document:

| Point | Novelty | Inventive | Tech Contrib. | Commercial | Scalability | Market | Defensibility | **Weighted Score** | Band |
|---|---|---|---|---|---|---|---|---|---|
| 1. Closed-loop lifecycle detection | 9 | 8 | 9 | 7 | 8 | 7 | 8 | **81.5** | Good Candidate |
| 4. Adaptive feedback loop | 8 | 7 | 8 | 7 | 7 | 6 | 8 | **73.5** | Needs Refinement (borderline) |
| 2. Multi-signal relationship decay | 7 | 7 | 7 | 7 | 7 | 6 | 6 | **68.5** | Needs Refinement |
| 3. Calendar action generation | 5 | 5 | 6 | 6 | 7 | 6 | 5 | **56** | Below 60 — consider trade secret |
| 6. Cross-channel reputation portability | 6 | 5 | 5 | 6 | 6 | 5 | 5 | **55** | Below 60 — speculative/future |
| 5. Persona taxonomy architecture | 4 | 4 | 5 | 6 | 8 | 5 | 4 | **49.5** | Below 60 — supportive/dependent claim only |

**This mostly confirms the earlier qualitative ranking**, with one reordering: Point 4 (adaptive feedback loop) now scores above Point 2 (relationship decay) rather than tied — the feedback loop's clearer technical-effect story (model adjustment from a defined signal) scores better under this more rigorous framework than relationship scoring's combinatorial-but-less-novel signal-blending.

**Practical implication:** Point 1 remains your primary/independent claim candidate. Point 3 (calendar generation) scoring below 60 reinforces that it's better framed as a dependent claim under Point 1, not pursued standalone.

---

## 17. Trade Secret vs. Patent Disclosure

**New decision, not previously made:** Patents require public disclosure of the invention. Two things in VachanAI should NOT go into any patent specification and should instead stay confidential trade secrets:
- The **exact few-shot prompt wording and specific examples** used in the extraction prompt (Section 7.5 of the AI Architecture doc) — the *method* (few-shot classification with a cross-referencing lifecycle check) is what gets patented; the specific prompt engineering that makes it work well is a trade secret, same way Coca-Cola's process is patented but the formula isn't.
- Any **specific threshold values** (decay score cutoffs, confidence thresholds) tuned through real pilot data — these are implementation details that improve with iteration and are more valuably kept confidential than disclosed.

*Action: when a patent attorney drafts the actual specification, flag these two categories explicitly as "describe the mechanism, not the exact parameters."*

---

## 18–19. Financial Planning & CAC/LTV

**Resolution: Explicitly marked as not modeled, not silently absent.** No burn rate, runway, or CAC/LTV figures exist because there's no revenue or spend yet to model against — fabricating numbers now would be less useful than waiting for Phase 2's actual subscription revenue to model against real data. Revisit when Phase 2 launches.

---

## 20. Team Building Roles (Module 15/17)

**Resolution: N/A while solo.** Every role-planning section in Modules 15 and 17 assumes a multi-person team; explicitly marked not applicable until co-founders or hires exist, rather than left looking like an oversight.

---

## 21. Exit Strategy

**Resolution: Acknowledged, deferred indefinitely.** Far too early to plan for a semester project with no revenue yet. Noted as existing in the framework; genuinely nothing to decide today.

---

## 22. Business Model Canvas (Module 15)

**Resolution: Worth building now — low effort, real clarity value.**

| Block | VachanAI |
|---|---|
| Value Proposition | Never let a promise or relationship quietly slip — tracked automatically, acted on with your confirmation |
| Customer Segments | Phase 1: students; Phase 2: professionals; Phase 3: executives/enterprise |
| Channels | Phase 1: campus network/direct; Phase 2: subscription signup; Phase 3: enterprise sales |
| Customer Relationships | Self-serve (Phase 1-2), white-glove onboarding (Phase 3) |
| Revenue Streams | Freemium → subscription ($8-15/mo) → per-seat enterprise ($30-100+/seat/mo) |
| Key Activities | Extraction/lifecycle/scoring engine development, pilot testing, patent documentation |
| Key Resources | The closed-loop lifecycle detection mechanism (core IP), Woxsen campus distribution advantage |
| Key Partners | (Future) university career centers, patent attorney, Woxsen Acceleration Track/T-Hub |
| Cost Structure | LLM API costs, hosting (free/low-cost tier for Phase 1), future patent filing costs |

---

## 23. Investor Pitch Deck (Module 16)

**Resolution: Not needed yet.** No traction/revenue exists to pitch against — building a full investor deck now would be premature theater. The Mentor Review Brief and Validation Brief already built serve the current actual need (academic review, expert feedback). Revisit Module 16 in full once there's real pilot data and a genuine fundraising motion, not before.

---

## 24. Project Manager Module (17) — Right-Sized for Solo Dev

**Resolution: Adopt selectively.** Skip: formal sprint ceremonies, Work Breakdown Structure (Epic→Feature→Story→Task→Subtask), and the weighted Project Health Score — all built for coordinating a team, not a solo developer. **Adopt:** the running Decision Log (merges with the ADR log from item 1) and the existing week-by-week Execution Plan already serves as the informal roadmap/milestone tracker Module 17 asks for — no need to duplicate it in a separate formal project-management artifact.

---

## 25. Product Strategist Module (18) — Right-Sized for Solo Dev

**Resolution:** Skip formal OKRs (they shine for team alignment; less valuable solo) and the weighted Opportunity Assessment scorecard (useful once there are multiple competing feature ideas to rank against each other — not yet the case). **Adopt:** the simple **Now / Next / Later** roadmap format as a lightweight replacement for a more elaborate roadmap — genuinely useful even solo, and already roughly matches the Phase 1/2/3 structure we've been using, just renamed.

---

## Summary: What Actually Changes in Existing Docs

| Doc | Change |
|---|---|
| Database Design | Add `is_deleted`/`deleted_at` to `commitments` and `contacts` |
| API Design | Update response envelope to include `success` boolean |
| AI Architecture | Flag exact prompt wording + tuned thresholds as trade secret, not patent disclosure |
| Patentable Points | Add weighted scorecard, reorder Point 2/4 |
| (New) ADR_LOG.md | Create, backfill ~15 major decisions |
| (New) DR Plan | One paragraph, added to Database Design doc |
| Execution Plan | No structural change — already serves as the informal roadmap Module 17 asked for |

Everything else is a documented, deliberate deferral — not a gap.
