# VachanAI — UI/UX Design
### Module 06 (Lean, VachanAI-Scoped Version)

---

## 6.1 Design Principles Applied

Of the six principles in the master module (Simplicity, Consistency, Visibility, Feedback, Accessibility, Scalability), two matter disproportionately for VachanAI specifically:

- **Visibility** — the whole product exists to surface things a user would otherwise forget. If an at-risk commitment or a decaying relationship isn't immediately visible on dashboard load, the product has failed at its one job. Nothing important should require more than one click to see.
- **Feedback** — since every calendar action is confirmation-gated (never silent), the UI must make the confirm/dismiss action feel immediate and clearly resolved — a delayed or ambiguous confirmation state directly undermines the trust the confirmation-gating was designed to build.

---

## 6.2 Core User Journey (Student Mode)

```
Entry (OAuth connect Gmail/Slack)
        ↓
Onboarding (set persona = student, tag a few key contacts: professor/recruiter/teammate)
        ↓
Primary Task: Daily Digest (see what needs attention today)
        ↓
Secondary Task: Review Commitment List (drill into any at-risk item)
        ↓
Secondary Task: Confirm/Dismiss proposed Calendar Actions
        ↓
Secondary Task: Review Relationship Scores (spot a contact going cold)
        ↓
Retention: Return daily for the digest; occasional deep dives into commitment/contact detail
```

**Why the digest is the entry point, not the commitment list:** a new user shouldn't land on a raw list they have to parse — the digest is the pre-summarized, prioritized view, and everything else is a drill-down from it. This mirrors how the product's core value (reducing what you have to remember) should also reduce what you have to look at.

---

## 6.3 Screen List

| Screen | Purpose |
|---|---|
| Connect Accounts | OAuth flow for Gmail, Slack, Google Calendar |
| Onboarding: Persona & Contacts | Set persona mode (student), tag initial key contacts |
| Daily Digest (Home) | Default landing screen — at-risk commitments, decaying relationships, upcoming deadlines |
| Commitment List | Full list, filterable by state (pending/at-risk/fulfilled/broken) |
| Commitment Detail | Single commitment view — source message, lifecycle history, manual override |
| Contacts / Relationships | List of contacts with current relationship score, sorted worst-first |
| Contact Detail | Single contact — score trend, related commitments, message history summary |
| Proposed Actions (Calendar) | List of proposed calendar events/reminders awaiting confirm/dismiss |
| Settings | Persona mode toggle (student/professional/executive preview), contact importance weight overrides, connected accounts management |

*Deliberately not built yet: Admin screen, Reports/Analytics screen, multi-user/team screens — none of these are meaningful at single-user Phase 1 scale.*

---

## 6.4 Wireframes (Text)

### Daily Digest (Home)
```
┌─────────────────────────────────────────────┐
│ Header: VachanAI    [Persona: Student ▾]  ⚙ │
├───────────┬───────────────────────────────────┤
│ Sidebar    │  Today's Digest                    │
│ - Digest   │  ┌─────────────────────────────┐  │
│ - Commit-  │  │ ⚠ 2 commitments at risk       │  │
│   ments    │  │ ⚠ 1 relationship going cold   │  │
│ - Contacts │  │ 📅 3 upcoming deadlines        │  │
│ - Actions  │  └─────────────────────────────┘  │
│ - Settings │  [At-risk commitment cards...]     │
│            │  [Decaying contact cards...]       │
│            │  [Proposed actions awaiting confirm]│
└───────────┴───────────────────────────────────┘
```

### Commitment Detail
```
┌─────────────────────────────────────────────┐
│ ← Back      Commitment Detail                 │
├─────────────────────────────────────────────┤
│ "Send the project deck by Friday"             │
│ State: [At Risk ●]   Deadline: Fri, 6:00 PM   │
│ Contact: Prof. Sharma (role: professor)        │
│ Source message: [view original] ↗              │
│ Lifecycle: Pending → At-Risk (2 days ago)      │
│ [Mark Fulfilled Manually]  [Dismiss]           │
└─────────────────────────────────────────────┘
```

### Proposed Actions
```
┌─────────────────────────────────────────────┐
│ Proposed Calendar Actions                     │
├─────────────────────────────────────────────┤
│ "Reminder: Send deck to Prof. Sharma"          │
│ Proposed for: Fri, 5:00 PM                     │
│ [ Confirm ✓ ]     [ Dismiss ✕ ]                │
├─────────────────────────────────────────────┤
│ ...next proposed action...                     │
└─────────────────────────────────────────────┘
```

---

## 6.5 Component Hierarchy

| Component | Used In | Notes |
|---|---|---|
| `CommitmentCard` | Digest, Commitment List | Shows description, state badge, deadline countdown |
| `StateBadge` | CommitmentCard, Commitment Detail | Color-coded: pending (neutral), at-risk (amber), fulfilled (green), broken (red) |
| `ContactCard` | Digest, Contacts list | Shows name, role tag, composite score, trend arrow |
| `ScoreTrendIndicator` | ContactCard, Contact Detail | Small sparkline or simple up/down arrow — deliberately not a full chart at Phase 1, see 6.9 |
| `ActionConfirmRow` | Proposed Actions | Confirm/Dismiss buttons, proposed time, loading state on click |
| `DigestSummaryBar` | Digest (top) | The 3-line "at a glance" counts shown in the wireframe above |
| `EmptyState` | Any list when empty | "No commitments at risk — you're all caught up" style, positive framing (see 6.7) |
| `PersonaToggle` | Header, Settings | Switches between Student/Professional/Executive-preview modes |

**Reused, not duplicated:** `StateBadge` and `ScoreTrendIndicator` are the only two components that carry real domain logic (color/threshold mapping) — every other component is presentation-only, which keeps the domain logic in one place if scoring thresholds or state names ever change.

---

## 6.6 Design System (Applying Your Existing Preferences)

- **Visual style:** iOS-style glassmorphism (translucent cards, subtle blur, soft shadows) — consistent with your existing design language across other projects
- **Motion:** Framer Motion for state transitions — particularly the confirm/dismiss action on `ActionConfirmRow` (a satisfying, quick confirmation animation reinforces that the action actually happened, addressing the Feedback principle from 6.1) and the state-badge transition when a commitment moves from pending → at-risk
- **Color mapping (functional, not decorative):** amber = at-risk, red = broken, green = fulfilled, neutral gray = pending — kept to exactly these four functional colors plus your brand accent, deliberately avoiding the "too many colors" anti-pattern from the master module
- **Typography:** one clear hierarchy — digest summary numbers largest, card titles next, metadata (dates, contact names) smallest — since the whole point of the digest is fast scanning, not dense information display

---

## 6.7 Empty States (Specifically Designed, Not Generic)

Empty states here carry real emotional weight — a student's "no commitments at risk" state should feel like relief/reward, not a blank error-like void:

- **Digest, nothing at risk:** "You're all caught up — nothing needs attention today."
- **Contacts, no decaying relationships:** "All your key relationships are healthy."
- **Proposed Actions, none pending:** "No pending confirmations right now."
- **First-time user, no data yet:** "Connect Gmail or Slack to start tracking your commitments" (with a clear connect button, not just an explanation)

---

## 6.8 Accessibility (Phase 1 Level)

- All state/status information (`StateBadge`, `ScoreTrendIndicator`) is conveyed with both color AND text/icon — never color alone, since amber/red/green distinctions fail for colorblind users if color is the only signal
- All interactive elements (confirm/dismiss buttons, card click-throughs) are keyboard-navigable and have visible focus states
- Minimum touch target size of 44×44px on the Confirm/Dismiss buttons specifically, since these are the highest-stakes interactions in the product

*Deferred: full WCAG AA audit, screen-reader-specific ARIA labeling pass, and multi-language support — worth doing properly once there's a broader pilot user base to test with, not simulated for a single-developer semester build.*

---

## 6.9 What's Deliberately NOT Built Yet (and why)

| Deferred Item | Why It's Premature for Phase 1 |
|---|---|
| Full analytics/reporting dashboard with charts | No user has enough historical data yet for trend charts to be meaningful over a few weeks of pilot use |
| Dark theme | Nice-to-have, not core to validating the product's actual value proposition |
| Mobile-native app | Responsive web is sufficient for pilot testing; native app is a Phase 2+ distribution decision, not a Phase 1 necessity |
| Full ScoreTrendIndicator charting (vs. simple arrow) | A full sparkline/chart needs more historical data points than a few weeks of pilot data will produce |
| Admin/multi-user management screens | Single-user Phase 1 has no multi-user administration need |

---

## 6.10 Evolution Path (Phase 2/3)

| Trigger | Change |
|---|---|
| Professional Mode launches (Phase 2) | Add CRM-style contact tagging UI, richer filtering on Commitment List |
| Enough historical data accumulates | Upgrade `ScoreTrendIndicator` from arrow to real sparkline/chart |
| Executive Mode launches (Phase 3) | Add enterprise-appropriate density (more information per screen, less "friendly" empty-state copy, more formal tone) — executives want density and control, not encouragement |
| Broader pilot beyond your immediate network | Run a real accessibility audit and add full ARIA labeling |
| Distribution shifts toward mobile-first usage | Evaluate React Native or a dedicated mobile build |

---

*This is the lean, VachanAI-scoped version of the UI/UX Designer module. The full generalized version (complete design token system, full component prop/state/variant documentation, WCAG-complete accessibility spec) can be built later by expanding the reasoning patterns already established here.*
