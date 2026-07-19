# VachanAI — Execution Plan
### Semester Build: Week-by-Week Roadmap (Phase 1 / Student Mode)

---

## Week 0: Setup (Before Development Starts)

**Goal:** Everything is ready so Week 1 is spent building, not configuring accounts.

- [ ] Set up Google Cloud project → enable Gmail API + Google Calendar API, generate OAuth credentials
- [ ] Set up Slack app + bot token (developer workspace is fine for testing)
- [ ] Get Claude/GPT API key, set a usage budget alert
- [ ] Set up GitHub repo (README, .gitignore, LICENSE, CLAUDE.md — you already have this pattern from FlyRank)
- [ ] Set up local dev environment: Python + FastAPI, PostgreSQL (local or free-tier hosted), Chroma
- [ ] Set up a simple project tracker (Notion/Trello/GitHub Projects) mirroring this week-by-week plan
- [ ] Recruit 3–5 early pilot volunteers from your network (Dean Fellow / Student Ambassador contacts) who'll agree to test with real inbox data later — line them up now, activate them in Week 9

**Deliverable:** Working local dev environment + all API keys tested with a "hello world" call each.

---

## Weeks 1–2: Problem Validation + Test Data

**Goal:** Before writing extraction logic, know what "correct" looks like.

- Pull 100–150 real messages (your own email/Slack, plus any volunteer-shared samples) representing realistic student commitment scenarios
- Manually label each message segment: commitment / not-a-commitment, and if a commitment: made-by-me / made-to-me / conditional / vague
- Define the Student Mode taxonomy: contact role tags (professor, recruiter, teammate, mentor) and their default importance weights
- Write the first version of the extraction prompt (few-shot, using ~10 labeled examples)

**Deliverable:** A labeled test set (spreadsheet/JSON) + v1 extraction prompt + taxonomy config file.

**Checkpoint:** Can you, reading the labeled set, describe in one sentence what makes something a "commitment" vs. just an update? If not, the taxonomy isn't tight enough yet — fix before moving on.

---

## Weeks 3–5: Commitment Extraction Engine

**Goal:** A working extraction pipeline you can trust.

- Week 3: Build the ingestion layer (Gmail + Slack API pull → normalized message schema)
- Week 4: Wire up the extraction agent (LLM call + classification), run against your labeled test set, measure precision/recall
- Week 5: Iterate on the prompt/few-shot examples based on errors; re-test until precision is comfortably above 80% on your labeled set

**Deliverable:** Extraction engine achieving your target accuracy on the labeled test set, with results logged.

**Checkpoint:** If accuracy plateaus below target after 2–3 iteration rounds, don't keep tuning blindly — go back to the taxonomy definition (Weeks 1–2) and check if the categories themselves are ambiguous.

---

## Weeks 6–8: Lifecycle Tracker + Cross-Referencing

**Goal:** Commitments update their own state without manual input — this is your core patentable mechanism, so it's worth the three full weeks.

- Week 6: Build the state machine (pending → approaching-deadline → at-risk → fulfilled/broken) and the Commitment/Message data model in PostgreSQL
- Week 7: Build the cross-referencing logic — when a new message arrives, check it against all open commitments (not just its own thread) for evidence of fulfillment
- Week 8: Test against realistic scenarios: a commitment fulfilled in a different thread, a commitment that goes stale, a commitment resolved by someone else's reply

**Deliverable:** A working lifecycle tracker with test cases demonstrating auto-resolution.

**Checkpoint:** Can the system correctly resolve a commitment when the fulfilling message is in a completely different conversation thread than where the promise was made? If not, this is the single most important thing to get right before moving on — it's your strongest differentiation and patent claim.

---

## Weeks 9–10: Relationship Decay Scoring

**Goal:** A believable, actionable relationship-health signal.

- Week 9: Activate your pilot volunteers (from Week 0) — get read access to enough real message history to compute meaningful trends
- Build the scoring model: response-latency trend + frequency trend + sentiment trend, weighted by role/importance
- Week 10: Tune the decay threshold so alerts feel meaningful, not noisy (test with volunteers: "does this alert match your gut feeling about this relationship?")

**Deliverable:** Working scoring engine + volunteer feedback on alert accuracy/usefulness.

**Checkpoint:** If volunteers say alerts feel random or annoying, the weighting is off before the threshold is — revisit which signals matter most for student relationships specifically (a slow-replying recruiter matters more than a slow-replying classmate).

---

## Week 11: Calendar Action Layer + Reminders

**Goal:** Close the loop from "detected" to "acted on."

- Build the proposed-action object (event/reminder) generated from a commitment with an inferred deadline
- Build the confirm-before-write flow (one-click accept/dismiss)
- Build escalating reminder logic tied to lifecycle state (soft nudge → urgent nudge)
- Wire up Google Calendar API for the actual write-on-confirm

**Deliverable:** End-to-end flow: commitment detected → action proposed → user confirms → calendar event created.

---

## Week 12: Dashboard + Digest UI

**Goal:** Make everything built so far visible and usable.

- Build the React dashboard: commitment list (by state), relationship score view, daily/weekly digest
- Apply your glassmorphism/Framer Motion design language
- Include a lightweight Executive Mode preview screen (mockup only, synthetic data) — this is your "here's how this scales" artifact for pitches, not a working feature

**Deliverable:** A usable, demoable dashboard.

---

## Weeks 13–14: Real-World Testing + Documentation

**Goal:** Prove it works on real data, and write everything up.

- Run the full system against your pilot volunteers' real (opted-in) data for 1–2 weeks
- Collect structured feedback: extraction accuracy, alert usefulness, whether confirmed calendar actions actually got used
- Fix any critical bugs surfaced during real testing
- Write up: semester report, README, architecture documentation, patent-points reference (already drafted), final PRD/BRD/SDD polish

**Deliverable:** Tested system + complete documentation package + pilot feedback summary.

---

## Final Weeks: Presentation + Forward Planning

- Build the demo/pitch deck (use the Founder's Choice framing + phased persona story)
- Prepare the patent-landscape search request for a patent attorney (don't file yet — just prep the request)
- Decide, based on pilot feedback and your own bandwidth, whether Phase 2 (professional tier) is a near-term next step or a later one

**Deliverable:** Final presentation, submitted semester project, and a clear "go/no-go/when" decision on scaling.

---

## Cross-Cutting Checkpoints (Apply Every Few Weeks)

- **Scope check:** Are you still building only what's in the Phase 1 scope (Section "Out of Scope" in the PRD), or has LinkedIn/WhatsApp/auto-send crept back in? If yes, cut it — that's a Phase 2/3 decision, not now.
- **Patent documentation:** Keep dated notes/commits as you go — this is your evidence trail if you file later. Don't wait until the end to reconstruct it.
- **Nebulytix conflict check:** Periodically confirm nothing from your internship work has been reused here, especially as you build the extraction/scoring logic.

---

## What Happens After the Semester (High-Level, Not Detailed Yet)

1. Review pilot feedback and decide whether to pursue provisional patent filing before any public/demo disclosure beyond your mentor/pitch reviews already done
2. If pursuing Phase 2: begin LinkedIn approved-API access process, build subscription billing, expand taxonomy to Professional Mode
3. If pursuing funding/incubation: use the Woxsen Acceleration Track / T-Hub connections already in motion, with this semester's working prototype and pilot data as proof

*This plan assumes solo execution at a sustainable pace. If your Nebulytix internship or coursework load spikes in a given week, the Weeks 3–5 and 6–8 blocks (extraction + lifecycle tracker) are the two that most need uninterrupted focus — protect those first if trade-offs are needed.*
