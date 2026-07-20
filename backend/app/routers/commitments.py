"""
API routes — Stage 4 demo scope only: submit a message, list commitments,
get today's digest. Full production scope (auth, pagination, relationship
scoring, calendar actions) is documented in docs/04_API_Design.md but not
built here — see Reconciliation Addendum Item 24 on right-sizing for a
solo demo build.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.db_models import Commitment
from app.schemas.api import ApiResponse, CommitmentOut, DigestOut, MessageIn
from app.services.message_processor import (
    _get_demo_user_id,
    process_incoming_message,
    refresh_deadline_states,
)

router = APIRouter()


@router.post("/messages", response_model=ApiResponse)
def submit_message(payload: MessageIn, db: Session = Depends(get_db)):
    """
    The core demo endpoint: submit a message, and the full closed loop
    (Extraction + Lifecycle cross-referencing) runs against it for real.
    """
    result = process_incoming_message(db, payload.body)
    return ApiResponse(data=result.model_dump())


@router.get("/commitments", response_model=ApiResponse)
def list_commitments(
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    user_id = _get_demo_user_id(db)
    refresh_deadline_states(db, user_id)

    query = db.query(Commitment).filter(
        Commitment.user_id == user_id, Commitment.is_deleted.is_(False)
    )
    if state:
        query = query.filter(Commitment.state == state)

    commitments = query.order_by(Commitment.created_at.desc()).all()
    data = [CommitmentOut.model_validate(c).model_dump() for c in commitments]
    return ApiResponse(data=data)


@router.get("/digest/today", response_model=ApiResponse)
def get_digest(db: Session = Depends(get_db)):
    """
    Read-only summary (per UI/UX doc Section 6.2 — the digest is the entry
    point, not the raw commitment list).
    """
    user_id = _get_demo_user_id(db)
    refresh_deadline_states(db, user_id)

    base = db.query(Commitment).filter(
        Commitment.user_id == user_id, Commitment.is_deleted.is_(False)
    )

    at_risk = base.filter(Commitment.state == "at-risk").all()
    pending = base.filter(Commitment.state == "pending").all()
    fulfilled = base.filter(Commitment.state == "fulfilled").all()

    digest = DigestOut(
        at_risk_count=len(at_risk),
        pending_count=len(pending),
        fulfilled_today_count=len(fulfilled),
        at_risk_commitments=[CommitmentOut.model_validate(c) for c in at_risk],
        upcoming_commitments=[CommitmentOut.model_validate(c) for c in pending],
    )
    return ApiResponse(data=digest.model_dump())
