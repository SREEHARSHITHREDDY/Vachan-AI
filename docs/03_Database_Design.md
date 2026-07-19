# VachanAI — Database Design
### Module 04 (Lean, VachanAI-Scoped Version)

---

## 4.1 Database Selection

**Choice: PostgreSQL (relational) + Chroma (vector/embedded, for semantic search)**

**Why relational for the core data:** Commitments, contacts, and their lifecycle states are inherently structured, relational records with clear foreign-key relationships (a commitment belongs to a user and a contact, a calendar action belongs to a commitment). This is a textbook relational use case — no document-store flexibility is needed since the schema is well-understood and stable for Phase 1.

**Why a separate vector store for semantic context:** Retrieving "messages semantically similar to this commitment" (for the lifecycle cross-referencing check) benefits from embedding-based similarity search, which relational databases don't do natively. Keeping this as a second, purpose-built store (rather than trying to bolt vector search onto Postgres via an extension) keeps each store doing the one thing it's good at.

**Deferred for later phases:** `pgvector` extension (to consolidate both into Postgres once Phase 2/3 volume justifies simplifying the stack) and a managed vector DB (Pinecone/Weaviate) once local Chroma no longer scales — see Section 4.8.

---

## 4.2 Entity-Relationship Diagram (Text)

```
┌──────────────┐        ┌──────────────┐        ┌──────────────────┐
│    User        │1     n│   Contact      │1     n│    Message         │
│                │───────│                │───────│                    │
└───────┬────────┘       └───────┬────────┘       └─────────┬──────────┘
        │1                       │1                          │1
        │                        │                            │
        │n                       │n                           │n
┌───────▼────────┐       ┌───────▼────────────┐      ┌────────▼──────────┐
│ RelationshipScore│      │   Commitment         │◀────│ (source_message_id)│
│                  │      │                      │      └────────────────────┘
└──────────────────┘      └──────┬───────┬──────┘
                                  │1      │1
                                  │n      │n
                       ┌──────────▼──┐ ┌──▼──────────────────┐
                       │CalendarAction│ │ FeedbackCorrection  │
                       └──────────────┘ └──────────────────────┘
```

**Relationship notes:**
- One `User` has many `Contact` records (their address book, effectively).
- One `Contact` has many `Message` records (conversation history) and exactly one current `RelationshipScore` (recalculated in place, not versioned in Phase 1 — see 4.7 for why).
- One `Commitment` is linked to the `Message` it was extracted from (`source_message_id`), and can have many `CalendarAction` and `FeedbackCorrection` records over its lifetime (a commitment could get a reminder proposed more than once, or be corrected more than once).

---

## 4.3 Table Schemas

### `users`
| Column | Type | Constraints |
|---|---|---|
| user_id | UUID | PRIMARY KEY, default gen_random_uuid() |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| oauth_tokens | JSONB | NOT NULL (encrypted at rest — see 4.6) |
| persona_mode | VARCHAR(20) | NOT NULL, DEFAULT 'student', CHECK (persona_mode IN ('student','professional','executive')) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

### `contacts`
| Column | Type | Constraints |
|---|---|---|
| contact_id | UUID | PRIMARY KEY |
| user_id | UUID | NOT NULL, FOREIGN KEY → users(user_id) ON DELETE CASCADE |
| name | VARCHAR(255) | NOT NULL |
| email_or_handle | VARCHAR(255) | NOT NULL |
| role_tag | VARCHAR(50) | NOT NULL, CHECK (role_tag IN ('professor','recruiter','teammate','mentor','other')) |
| importance_weight | NUMERIC(3,2) | NOT NULL, DEFAULT 0.50, CHECK (importance_weight BETWEEN 0 AND 1) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

### `messages`
| Column | Type | Constraints |
|---|---|---|
| message_id | UUID | PRIMARY KEY |
| user_id | UUID | NOT NULL, FOREIGN KEY → users(user_id) ON DELETE CASCADE |
| contact_id | UUID | FOREIGN KEY → contacts(contact_id) ON DELETE SET NULL |
| channel | VARCHAR(20) | NOT NULL, CHECK (channel IN ('gmail','slack')) |
| direction | VARCHAR(10) | NOT NULL, CHECK (direction IN ('inbound','outbound')) |
| body_ref | TEXT | NOT NULL (message content or pointer to it) |
| sent_at | TIMESTAMPTZ | NOT NULL |
| ingested_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

### `commitments`
| Column | Type | Constraints |
|---|---|---|
| commitment_id | UUID | PRIMARY KEY |
| user_id | UUID | NOT NULL, FOREIGN KEY → users(user_id) ON DELETE CASCADE |
| contact_id | UUID | FOREIGN KEY → contacts(contact_id) ON DELETE SET NULL |
| source_message_id | UUID | NOT NULL, FOREIGN KEY → messages(message_id) |
| commitment_type | VARCHAR(20) | NOT NULL, CHECK (commitment_type IN ('made-by-me','made-to-me','conditional','vague')) |
| state | VARCHAR(20) | NOT NULL, DEFAULT 'pending', CHECK (state IN ('pending','approaching-deadline','at-risk','fulfilled','broken')) |
| inferred_deadline | TIMESTAMPTZ | NULLABLE |
| description | TEXT | NOT NULL (extracted commitment text) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| resolved_at | TIMESTAMPTZ | NULLABLE |

### `relationship_scores`
| Column | Type | Constraints |
|---|---|---|
| score_id | UUID | PRIMARY KEY |
| contact_id | UUID | NOT NULL, UNIQUE, FOREIGN KEY → contacts(contact_id) ON DELETE CASCADE |
| latency_trend | NUMERIC(6,2) | NOT NULL (e.g., avg response time in hours, trailing window) |
| frequency_trend | NUMERIC(6,2) | NOT NULL (messages/week, trailing window) |
| sentiment_trend | NUMERIC(3,2) | NOT NULL, CHECK (sentiment_trend BETWEEN -1 AND 1) |
| composite_score | NUMERIC(4,2) | NOT NULL |
| computed_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

*Note: `UNIQUE` on `contact_id` means this table stores the current score only, not history — see 4.7 on why history is deferred.*

### `calendar_actions`
| Column | Type | Constraints |
|---|---|---|
| action_id | UUID | PRIMARY KEY |
| commitment_id | UUID | NOT NULL, FOREIGN KEY → commitments(commitment_id) ON DELETE CASCADE |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'proposed', CHECK (status IN ('proposed','confirmed','dismissed')) |
| proposed_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| confirmed_at | TIMESTAMPTZ | NULLABLE |
| calendar_event_id | VARCHAR(255) | NULLABLE (populated only after confirmation) |

### `feedback_corrections`
| Column | Type | Constraints |
|---|---|---|
| correction_id | UUID | PRIMARY KEY |
| commitment_id | UUID | NOT NULL, FOREIGN KEY → commitments(commitment_id) ON DELETE CASCADE |
| user_verdict | VARCHAR(20) | NOT NULL, CHECK (user_verdict IN ('confirmed','rejected')) |
| corrected_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

---

## 4.4 Indexing Strategy

| Table | Index | Reason |
|---|---|---|
| messages | (user_id, contact_id, sent_at DESC) | Fast retrieval of a contact's message history in chronological order — used constantly by both extraction and scoring |
| commitments | (user_id, state) | The dashboard's primary query is "show me all at-risk/pending commitments for this user" |
| commitments | (contact_id) | Used when computing relationship scores tied to open commitments with a contact |
| calendar_actions | (status) | Used to find all "proposed" actions awaiting user confirmation |
| relationship_scores | (contact_id) UNIQUE | Already required by the uniqueness constraint; also serves as the lookup index |

No exotic indexing (partial indexes, GIN/GiST) is needed at Phase 1 volume — these five B-tree indexes cover every actual query pattern the application has.

---

## 4.5 Normalization

The schema above is in **Third Normal Form (3NF)** — no repeating groups, every non-key column depends on the whole primary key, and no transitive dependencies (e.g., `importance_weight` lives on `contacts`, not duplicated onto every `commitment` row that references that contact).

**One deliberate denormalization, explained:** `relationship_scores` stores a single current composite score per contact rather than requiring a join/aggregation over the full message history on every dashboard load. This is a standard "materialized computed value" pattern — the trade-off (score can be briefly stale between recompute cycles) is acceptable because relationship decay is inherently a slow-moving signal, not something that needs to be correct to the second.

---

## 4.6 Security & Encryption

- `oauth_tokens` (JSONB column on `users`) is encrypted at the application layer before being written to the database (not relying on Postgres-level encryption alone) — since this is the single most sensitive piece of data in the system (it's the key to the user's actual email/calendar).
- No plaintext passwords are ever stored — VachanAI relies entirely on OAuth, so there's no password table to protect in the first place.
- Row-level access is enforced at the application layer for Phase 1 (every query is scoped by `user_id` from the authenticated session) rather than via Postgres Row-Level Security policies — RLS is a Phase 3 addition once multi-tenant enterprise isolation actually requires database-level enforcement, not just application-level discipline.

---

## 4.7 What's Deliberately NOT Built Yet (and why)

| Deferred Item | Why It's Premature for Phase 1 |
|---|---|
| Score history/versioning table | Adds real complexity (time-series storage, retention policy) for a signal that's only useful in aggregate at pilot scale; revisit once you have enough longitudinal data to actually analyze trends-of-trends |
| Partitioning/sharding | Phase 1 has single-digit-thousands of rows at most; partitioning a table this size adds operational complexity with zero performance benefit |
| Multi-tenant schema isolation (separate schemas per enterprise customer) | Only relevant once Phase 3 has enterprise customers requiring data isolation guarantees beyond row-level `user_id` scoping |
| Full migration tooling (e.g., Alembic with rollback testing) | A lightweight migration approach (simple versioned SQL files) is sufficient for a single-developer, single-environment Phase 1 — full migration tooling pays off once multiple environments/collaborators exist |
| Read replicas / caching layer (Redis) | No read-volume problem exists yet to justify this; premature optimization for a pilot user base |

---

## 4.8 Evolution Path (Phase 2/3)

| Trigger | Change |
|---|---|
| Chroma outgrows local/embedded use | Migrate to managed vector DB (Pinecone/Weaviate) or add `pgvector` extension to consolidate into Postgres |
| Multiple developers/environments | Adopt proper migration tooling (Alembic) with tested rollback paths |
| Enterprise customers (Phase 3) | Add Postgres Row-Level Security policies as a database-enforced layer on top of (not instead of) application-level scoping |
| Relationship trend analysis becomes a real feature | Add a `relationship_score_history` table, likely with a retention/rollup policy (keep daily granularity for 90 days, weekly rollups beyond that) |
| Read load grows significantly | Introduce a read replica and/or Redis caching layer for the most frequent queries (dashboard load, digest generation) |

---

*This is the lean, VachanAI-scoped version of the Database Designer module. The full generalized version (covering NoSQL selection criteria, sharding strategy, multi-tenant patterns in depth, etc.) can be built later by extracting and expanding the reasoning patterns already established here.*
