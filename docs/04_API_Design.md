# VachanAI — API Design
### Module 05 (Lean, VachanAI-Scoped Version)

---

## 5.1 API Design Philosophy

**Choice: REST over GraphQL or WebSockets for Phase 1.**

VachanAI's data access patterns are simple and resource-shaped (get my commitments, get my relationship scores, confirm a calendar action) rather than requiring flexible client-defined queries (GraphQL's strength) or real-time bidirectional streams (WebSocket's strength). The dashboard polls/refreshes on a normal request-response cycle — there's no chat-like or live-collaboration feature that would justify the added complexity of either alternative at this stage. REST is also the fastest to build, test, and document for a solo developer on a semester timeline.

**Deferred:** WebSockets become worth adding in Phase 2/3 if live notification push (rather than polling) becomes a real user-experience requirement at scale — noted in Section 5.7.

---

## 5.2 Versioning Strategy

All endpoints are prefixed `/api/v1/...`. Version is bumped only on breaking changes (field removal, semantic change to an existing field) — additive changes (new optional fields, new endpoints) don't require a version bump. For a single-developer, single-client (your own React dashboard) Phase 1 system, this is intentionally lightweight; stricter deprecation-window policies become relevant once Phase 2 has external API consumers who aren't you.

---

## 5.3 Authentication & Authorization

- **Authentication:** OAuth 2.0 via Google (covers Gmail + Calendar) and Slack's own OAuth flow. VachanAI never handles or stores user passwords directly.
- **Session handling:** short-lived JWT issued after OAuth completes, used as a Bearer token on all subsequent API calls.
- **Authorization:** every endpoint scopes its query by the `user_id` embedded in the JWT — there is no endpoint that can return another user's data, enforced at the application layer for Phase 1 (see Database Design doc, Section 4.6, on why DB-level Row-Level Security is deferred to Phase 3).

---

## 5.4 Core Endpoints

### Commitments

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/commitments` | List commitments for the authenticated user, filterable by `state` |
| GET | `/api/v1/commitments/{commitment_id}` | Get a single commitment's detail |
| PATCH | `/api/v1/commitments/{commitment_id}` | Manual override of state (e.g., user manually marks something fulfilled) |

**Example — GET /api/v1/commitments?state=at-risk**

Request headers: `Authorization: Bearer <jwt>`

Response 200:
```json
{
  "data": [
    {
      "commitment_id": "c1a2...",
      "contact_id": "ct91...",
      "commitment_type": "made-by-me",
      "state": "at-risk",
      "description": "Send the project deck by Friday",
      "inferred_deadline": "2026-07-18T18:00:00Z",
      "created_at": "2026-07-14T09:12:00Z"
    }
  ],
  "meta": { "count": 1 }
}
```

### Contacts / Relationships

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/contacts` | List contacts with current relationship scores |
| GET | `/api/v1/contacts/{contact_id}` | Get a single contact's detail + score trend |
| PATCH | `/api/v1/contacts/{contact_id}` | Update role_tag / importance_weight |

### Calendar Actions

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/actions?status=proposed` | List actions awaiting user confirmation |
| POST | `/api/v1/actions/{action_id}/confirm` | Confirm a proposed action → triggers Calendar API write |
| POST | `/api/v1/actions/{action_id}/dismiss` | Dismiss a proposed action → no write occurs |

**Example — POST /api/v1/actions/{action_id}/confirm**

Response 200:
```json
{
  "action_id": "a771...",
  "status": "confirmed",
  "calendar_event_id": "evt_8x2k..."
}
```

Response 409 (already resolved):
```json
{
  "error": {
    "code": "ACTION_ALREADY_RESOLVED",
    "message": "This action has already been confirmed or dismissed."
  }
}
```

### Digest

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/digest/today` | Get today's compiled digest (at-risk commitments, decaying relationships, upcoming deadlines) |

### Feedback

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/v1/commitments/{commitment_id}/feedback` | User confirms/rejects whether a flagged item was a real commitment (feeds FR-10's adaptive loop) |

---

## 5.5 Pagination, Filtering, Sorting

- **Pagination:** cursor-based (`?cursor=<opaque_token>&limit=20`), not offset-based — cheaper on Postgres as tables grow, and avoids the "page 2 shifts because new rows were inserted" problem offset pagination has.
- **Filtering:** query parameters map directly to indexed columns where possible (e.g., `?state=at-risk` uses the `(user_id, state)` index from the Database Design doc) — filters that aren't backed by an index are avoided in Phase 1 rather than allowed to silently degrade performance.
- **Sorting:** default sort is always by the most operationally relevant field (commitments by `inferred_deadline` ascending, contacts by `composite_score` ascending — most-decayed relationships first) rather than requiring the client to specify sort on every call.

---

## 5.6 Error Response Standard

Every error follows one consistent shape:

```json
{
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Human-readable explanation",
    "field": "optional_field_name_if_validation_error"
  }
}
```

| HTTP Status | Used When |
|---|---|
| 400 | Malformed request (bad JSON, missing required field) |
| 401 | Missing/invalid/expired JWT |
| 403 | Valid JWT, but attempting to access another user's resource |
| 404 | Resource not found (or belongs to another user — same response as not-found, deliberately, to avoid leaking existence of other users' data) |
| 409 | Conflict (e.g., confirming an already-resolved action) |
| 429 | Rate limit exceeded |
| 500 | Unexpected server error |

**Design decision explained:** returning 404 (not 403) when a user requests another user's resource is deliberate — it avoids confirming to an attacker that a given `commitment_id` exists at all, which is a small but real information-leakage difference worth getting right from day one even in a semester project.

---

## 5.7 Idempotency & Rate Limiting

- **Idempotency:** `POST /actions/{action_id}/confirm` is naturally idempotent by design — confirming an already-confirmed action returns the same 409 response rather than creating a duplicate calendar event. No separate idempotency-key header mechanism is needed at Phase 1 scale; that becomes worth adding once Phase 2 has payment or higher-stakes write operations where a duplicate write is costlier.
- **Rate limiting:** a simple per-user request cap (e.g., 100 requests/minute) is enough to protect the LLM-API-cost-sensitive endpoints for Phase 1 (a single pilot user can't accidentally rack up a large API bill by hammering an endpoint). Tiered rate limits by subscription plan become relevant in Phase 2 when there's an actual paid-tier distinction to enforce.

---

## 5.8 OpenAPI/Swagger

FastAPI generates OpenAPI documentation automatically from the route definitions and Pydantic models — no separate spec-writing effort is needed for Phase 1; the interactive `/docs` endpoint FastAPI provides out of the box is sufficient for a solo developer and small pilot group. Publishing a versioned, hand-curated OpenAPI spec as a standalone artifact becomes worth it once Phase 2 has external developers integrating against the API.

---

## 5.9 What's Deliberately NOT Built Yet (and why)

| Deferred Item | Why It's Premature for Phase 1 |
|---|---|
| GraphQL endpoint | No client need for flexible querying yet — one client (your own dashboard) with known, stable data needs |
| WebSocket push notifications | Polling is sufficient at pilot scale; real-time push adds real infrastructure complexity (connection management, scaling) not justified yet |
| Formal idempotency-key headers | Natural idempotency (via status checks) covers Phase 1's actual write operations |
| Tiered/plan-based rate limiting | No paid tiers exist yet to differentiate between |
| Published, versioned OpenAPI spec as a separate artifact | Auto-generated `/docs` is sufficient with a single internal client |

---

## 5.10 Evolution Path (Phase 2/3)

| Trigger | Change |
|---|---|
| External developers/partners integrate against the API | Publish a hand-curated, versioned OpenAPI spec; add formal deprecation-window policy |
| Paid subscription tiers launch | Add tiered rate limiting by plan |
| Users want live updates without refreshing | Add WebSocket channel for digest/commitment-state push updates |
| Payment or other high-stakes writes introduced | Add explicit idempotency-key header support beyond natural idempotency |
| Multiple client types emerge (mobile app, third-party integrations with varying data needs) | Reconsider GraphQL as a complementary layer for flexible querying |

---

*This is the lean, VachanAI-scoped version of the API Architect module. The full generalized version (deep GraphQL guidance, WebSocket architecture patterns, full API lifecycle management) can be built later by expanding the reasoning patterns already established here.*
