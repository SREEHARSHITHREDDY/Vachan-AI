"""
API-layer request/response schemas — deliberately separate from
schemas/commitment.py and schemas/lifecycle.py, which model the LLM's
structured output. These model the HTTP contract instead, matching the
response envelope decided in the Reconciliation Addendum (Item 4):
{"success": bool, "data"|"error": ...}.

Kept minimal for the Stage 4 demo scope — no auth, no pagination, no
filtering beyond a single optional `state` query param. The full API
Design doc (docs/04_API_Design.md) describes the production-scope version;
this is deliberately the smallest slice that makes the frontend possible.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class MessageIn(BaseModel):
    """
    What the frontend sends when a user submits something to process.

    channel now covers more than typed text: a user can log a phone call
    or an in-person conversation too — the extraction/lifecycle mechanism
    doesn't care how the words were captured, only what they say. For a
    call/in-person entry, `body` is expected to be the user's own summary
    of what was said/promised, not a verbatim transcript (that distinction
    matters for how reliable the source material is, but doesn't change
    how the pipeline processes it).
    """

    body: str
    channel: Literal["message", "call", "in-person"] = "message"


class CommitmentUpdate(BaseModel):
    """
    Manual override request body — lets the user mark a commitment's
    state directly, and/or set or edit its deadline, without needing a
    second message to trigger the LLM cross-referencing check.

    state now includes "at-risk" as a valid manual target (not just
    pending/fulfilled): a user can flag something urgent by judgment
    call even when the deadline math (see AT_RISK_THRESHOLD_HOURS in
    lifecycle_service.py) wouldn't have flagged it automatically yet.
    The reverse direction — moving OFF at-risk back to pending — is only
    ever this kind of explicit action too; the automatic deadline-proximity
    refresh (refresh_deadline_states) deliberately never reverts it on its
    own, so a manual call here is the only way back to pending once
    something's been flagged.

    Both fields are optional and independent: a request can update state
    only, deadline only, or both together in one call.
    """

    state: Optional[Literal["pending", "at-risk", "fulfilled"]] = None
    inferred_deadline: Optional[datetime] = None


class CommitmentOut(BaseModel):
    commitment_id: str
    commitment_type: str
    state: str
    description: str
    inferred_deadline: Optional[datetime] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    # NOT on the Commitment DB row itself — it lives on the related Message
    # (source_message_id). Populated by whoever builds this response, not
    # by model_validate() alone; see message_processor.py and the
    # commitments router for where it's actually filled in.
    channel: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MessageProcessResult(BaseModel):
    """
    Response after submitting a message: what was extracted (if anything)
    and what was resolved (if anything) — lets the frontend show both
    halves of the closed-loop mechanism in one response.
    """

    new_commitment: Optional[CommitmentOut] = None
    resolved_commitment_id: Optional[str] = None
    resolution_reasoning: Optional[str] = None


class DigestOut(BaseModel):
    at_risk_count: int
    pending_count: int
    fulfilled_today_count: int
    at_risk_commitments: list[CommitmentOut]
    upcoming_commitments: list[CommitmentOut]


class ApiResponse(BaseModel):
    """Generic success envelope — {"success": true, "data": ...}."""

    success: bool = True
    data: Any = None


class ApiError(BaseModel):
    """Generic error envelope — {"success": false, "error": {...}}."""

    success: bool = False
    error: dict[str, str]
