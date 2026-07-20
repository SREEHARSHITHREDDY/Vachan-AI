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
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class MessageIn(BaseModel):
    """What the frontend sends when a user submits a new message to process."""

    body: str
    channel: str = "manual"  # demo scope: no real Gmail/Slack ingestion, user pastes text


class CommitmentOut(BaseModel):
    commitment_id: str
    commitment_type: str
    state: str
    description: str
    inferred_deadline: Optional[datetime] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

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
