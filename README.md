# VachanAI

Agentic AI Commitment & Relationship Intelligence Engine.

This repo is scaffolded from the full VachanAI documentation set (BRD/PRD/SDD,
Database Design, API Design, UI/UX Design, AI Architecture, Execution Plan,
and the Reconciliation Addendum). See `/docs` for the full spec — this
codebase should stay in sync with those documents, not drift from them.

## Current Status

**First module implemented: Commitment Extraction Engine** (Execution Plan, Weeks 3-5).

This is the foundational service — everything else (Lifecycle Tracker,
Relationship Scoring, Calendar Action Layer, Digest) depends on it and
should be built next, in that order, per the Execution Plan.

## What's Here

```
vachanai/
├── ADR_LOG.md                  # Architecture Decision Record log (backfilled)
├── docs/                       # Copy your spec docs here for reference
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py       # Environment settings
│   │   │   └── llm_client.py   # Thin Anthropic API wrapper
│   │   ├── schemas/
│   │   │   └── commitment.py   # Pydantic models matching the DB schema
│   │   ├── services/
│   │   │   └── extraction_service.py   # <-- THE FIRST MODULE
│   │   ├── models/              # (empty — SQLAlchemy models, build next)
│   │   └── routers/             # (empty — FastAPI routes, build next)
│   ├── tests/
│   │   ├── test_extraction_service.py
│   │   └── fixtures/
│   │       └── labeled_test_set.json   # PLACEHOLDER — replace with real data
│   ├── requirements.txt
│   └── .env.example
└── frontend/                    # (empty — React dashboard, build after backend)
```

## Getting Started

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your real ANTHROPIC_API_KEY
```

## Running Tests

```bash
# Fast unit tests (mocked LLM, no API key needed, no cost)
pytest tests/test_extraction_service.py -v

# Live accuracy evaluation against the labeled test set (costs API credits)
# This is the actual Week 3-5 checkpoint from the Execution Plan.
pytest tests/test_extraction_service.py --run-live -v -s
```

## IMPORTANT: Before Trusting Any Accuracy Numbers

The few-shot examples in `extraction_service.py` (`FEW_SHOT_EXAMPLES`) and
the test fixture (`tests/fixtures/labeled_test_set.json`) are **illustrative
placeholders**, not real data. Per the Execution Plan (Weeks 1-2):

1. Pull 100-150 real messages from your own email/Slack + volunteer samples
2. Manually label each as commitment/not-commitment, with type
3. Replace both `FEW_SHOT_EXAMPLES` and `labeled_test_set.json` with real, labeled data
4. THEN run `--run-live` and trust the precision number it reports

Running the live eval against placeholder data will tell you nothing
meaningful about real-world accuracy.

## Next Modules to Build (in order)

1. ~~Commitment Extraction Engine~~ ✅ (this scaffold)
2. **Commitment Lifecycle Tracker** — state machine + cross-referencing (Weeks 6-8, the core patentable mechanism — see AI Architecture doc Section 7.6, Touchpoint 2)
3. **Relationship Decay Scoring** (Weeks 9-10)
4. **Calendar Action Layer** (Week 11)
5. **Dashboard + Digest UI** (Week 12)

## Key Docs to Keep Handy While Building

- `AI Architecture doc` — prompt design reasoning, security guardrails (read before touching `extraction_service.py`)
- `Database Design doc` — exact schema this code must match
- `API Design doc` — endpoint contracts for when routers get built
- `Reconciliation Addendum` — the tie-breaker for anything that looks inconsistent
- `ADR_LOG.md` — why things are built the way they are

## License

Not yet decided — add before any public/open-source release.
