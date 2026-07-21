# VachanAI — Future Roadmap: Auth, Connectors & UI Vision
### Phase 2/3 Requirements (Documented, Not Built for the July 27th Demo)

This document exists so these requirements are captured and traceable — not lost between now and whenever Phase 2 actually starts — without putting any of them in scope for the current demo build.

---

## 1. Authentication (Login / Signup)

**Requirement:** Real user accounts — login and signup pages, not the current single fixed demo user.

**What this actually involves when built for real:**
- Password hashing (or OAuth-only auth, which may be preferable given Gmail is already an OAuth dependency)
- Session/JWT handling
- A security review before any real user data is at stake
- Corresponding backend changes: every route currently scoped to a single hardcoded demo user (`_get_demo_user_id()` in `message_processor.py`) needs to become properly per-user

**Why deferred:** The Reconciliation Addendum (Item 24) and the API Design doc both explicitly scoped auth out of Phase 1 — proving the core extraction/lifecycle mechanism didn't require it. This remains the right call for a semester demo; it becomes necessary the moment this handles more than one real user's data.

---

## 2. Real Connector Integrations

### Gmail
**Requirement:** Real OAuth-based Gmail ingestion, replacing the current manual text-paste input.

**What this involves:** Google Cloud OAuth app registration, consent screen setup, encrypted token storage (flagged as a real security requirement, not optional), token refresh handling, and actual message-polling/webhook logic.

**Feasibility note:** This is the most achievable of the three connectors — Gmail's API is well-documented and doesn't require third-party business approval, just proper implementation time.

### WhatsApp
**Requirement:** Real WhatsApp message ingestion.

**Feasibility note — important:** This was flagged multiple times earlier in this build for a reason that hasn't changed: **WhatsApp Business API requires Meta's approval process and a paid Business Solution Provider relationship.** This is not something that can be self-provisioned quickly regardless of available development time — it involves an external approval process outside anyone's direct control.

### "Other" Connectors
**Requirement:** Left open-ended in the request — likely candidates based on the original AI Architecture doc's scope: Slack (already partially designed for), SMS, calendar systems.

**Recommendation when this phase starts:** Prioritize by actual user research (which channel do real pilot users' commitments actually come from most) rather than building all of them speculatively.

---

## 3. UI/UX Vision — "World-Class" Design System

A detailed design brief was provided (referenced in full in chat history around July 21st) targeting the polish level of Apple, Linear, Notion, Stripe Dashboard, Arc, Figma, and similar best-in-class products. Key elements worth preserving for when there's real time to invest in this:

- Full design system: consistent spacing/radii/shadows/typography/iconography/motion, documented
- Command palette, drag-and-drop calendar (agenda/timeline/weekly/monthly views)
- Progress rings, streaks, momentum indicators (used tastefully, not over-gamified)
- Virtualized tables, optimistic UI, skeleton loading states
- Mobile-first (not just responsive) experience
- WCAG AA accessibility as a baseline requirement, not an afterthought
- AI integration that feels contextual and assistive, never intrusive

**Honest assessment:** This level of polish is realistically months of dedicated design + engineering work, not a rebuild pass. The current frontend (sidebar nav, dark/light theme, channel-aware commitment tracking) is a reasonable, functional MVP-level interface — a legitimate stepping stone toward this vision, not a placeholder to be ashamed of in the meantime.

---

## Suggested Sequencing (When Phase 2 Actually Starts)

1. Auth first — nothing else in this list works safely without it
2. Gmail connector (most achievable, no external approval blocker)
3. Design system investment — ideally informed by real Phase 1 pilot usage data, so effort goes where users actually spend time
4. WhatsApp connector — timeline depends entirely on Meta's approval process, so start that conversation early if it's a priority
5. Additional connectors — prioritized by actual demand, not built speculatively

---

*This document deliberately makes no code changes. It exists purely so this scope is tracked and doesn't get lost, while keeping the July 27th demo build stable and untouched.*
