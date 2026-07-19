"""
Pydantic schemas for the Commitment entity.

These mirror the `commitments` table defined in the VachanAI Database Design
doc (Section 4.3), plus the extraction-specific fields (confidence) that the
LLM extraction call produces but that aren't persisted directly.

Field names and enums are kept in exact sync with the database schema so
that an ExtractionResult can be mapped straight onto a Commitment row
without any translation layer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CommitmentType(str, Enum):
    """Matches the commitment_type CHECK constraint in the DB schema."""

    MADE_BY_ME = "made-by-me"
    MADE_TO_ME = "made-to-me"
    CONDITIONAL = "conditional"
    VAGUE = "vague"


class CommitmentState(str, Enum):
    """Matches the state CHECK constraint in the DB schema."""

    PENDING = "pending"
    APPROACHING_DEADLINE = "approaching-deadline"
    AT_RISK = "at-risk"
    FULFILLED = "fulfilled"
    BROKEN = "broken"


class ConfidenceLevel(str, Enum):
    """
    Not persisted to the DB directly — used by the UI to decide whether to
    surface a low-confidence extraction differently (per AI Architecture
    doc, Section 7.5's guardrail on avoiding false certainty).
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractionResult(BaseModel):
    """
    The structured output the LLM extraction call must return.

    This is intentionally the ONLY shape the extraction service accepts
    from the LLM — per AI Architecture doc Section 7.5, output is
    structured JSON only, never free text, so it can be validated before
    being written anywhere.
    """

    is_commitment: bool = Field(
        ..., description="Whether this message segment contains a commitment at all."
    )
    commitment_type: Optional[CommitmentType] = Field(
        None, description="Required if is_commitment is True; null otherwise."
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Short, extracted description of the commitment, e.g. "
        "'Send the project deck by Friday'.",
    )
    inferred_deadline: Optional[datetime] = Field(
        None, description="Deadline inferred from message content, if any."
    )
    confidence: ConfidenceLevel = Field(
        ..., description="Model's self-reported confidence in this classification."
    )

    model_config = ConfigDict(use_enum_values=True)


class CommitmentCreate(BaseModel):
    """What the extraction service passes to the DB layer to create a row."""

    user_id: UUID
    contact_id: Optional[UUID] = None
    source_message_id: UUID
    commitment_type: CommitmentType
    description: str
    inferred_deadline: Optional[datetime] = None
    state: CommitmentState = CommitmentState.PENDING


class CommitmentRead(BaseModel):
    """API response shape for a Commitment — matches the response envelope
    standard set in the Reconciliation Addendum (Item 4)."""

    commitment_id: UUID
    user_id: UUID
    contact_id: Optional[UUID]
    commitment_type: CommitmentType
    state: CommitmentState
    description: str
    inferred_deadline: Optional[datetime]
    created_at: datetime
    resolved_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
