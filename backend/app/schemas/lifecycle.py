"""
Pydantic schemas for the Lifecycle Tracker (Stage 2).

Kept in a separate file from schemas/commitment.py rather than editing that
file, since commitment.py is already committed and this is new, additive
functionality — cleaner git history than modifying an existing committed file.

Demo-scope note (per the 8-day evaluation plan): the full production design
(AI Architecture 7.6, Touchpoint 2) supports the full 5-state lifecycle
(pending -> approaching-deadline -> at-risk -> fulfilled -> broken). This
demo scope deliberately implements only pending -> at-risk -> fulfilled,
which is enough to prove the core patentable mechanism (cross-referencing
a new message against OPEN commitments to auto-detect fulfillment) without
building deadline-breach handling or the full state machine's edge cases
under an 8-day deadline.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.commitment import CommitmentState


class OpenCommitmentSummary(BaseModel):
    """
    The minimal view of an open commitment the Lifecycle Tracker needs to
    check a new message against. Deliberately NOT the full Commitment model
    — only what the cross-referencing LLM call actually needs to reason
    about, keeping the prompt small per AI Architecture 7.4 (token cost).
    """

    commitment_id: UUID
    description: str
    inferred_deadline: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ResolutionCheckResult(BaseModel):
    """
    Structured output of the cross-referencing check: does this new message
    resolve any of the currently open commitments?

    This is the core patentable mechanism (AI Architecture 7.6, Touchpoint 2;
    SDD Section 5.5) — auto-resolution from independent evidence in a
    DIFFERENT message than the one where the commitment was made, without
    requiring the user to manually mark anything as done.
    """

    resolved: bool = Field(
        ..., description="Whether this message resolves any open commitment."
    )
    resolved_commitment_id: Optional[UUID] = Field(
        None,
        description="Which open commitment was resolved, if any. Must be "
        "one of the IDs passed into the check — never a fabricated ID.",
    )
    reasoning: Optional[str] = Field(
        None,
        max_length=300,
        description="Brief explanation of why this message resolves (or "
        "doesn't resolve) the commitment — kept for debugging/audit, not "
        "shown to the end user by default.",
    )

    model_config = ConfigDict(use_enum_values=True)


class DeadlineCheckResult(BaseModel):
    """
    Output of the (non-LLM) deadline-proximity check. Deliberately separate
    from ResolutionCheckResult: this is plain date arithmetic, not a model
    call, and mixing the two would obscure which state transitions are
    LLM-driven (resolution) vs. purely mechanical (deadline proximity).
    """

    commitment_id: UUID
    new_state: CommitmentState
    hours_until_deadline: Optional[float] = None
