"""
API routes — Stage 4 demo scope only: submit a message, list commitments,
get today's digest. Full production scope (auth, pagination, relationship
scoring, calendar actions) is documented in docs/04_API_Design.md but not
built here — see Reconciliation Addendum Item 24 on right-sizing for a
solo demo build.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.db_models import Commitment, Message
from app.schemas.api import ApiResponse, CommitmentOut, CommitmentUpdate, DigestOut, MessageIn
from app.services.message_processor import (
    _get_demo_user_id,
    process_incoming_message,
    refresh_deadline_states,
)

router = APIRouter()


def _to_commitment_out_list(db: Session, commitments: list[Commitment]) -> list[CommitmentOut]:
    """
    Attaches each commitment's source channel (message/call/in-person) —
    channel lives on Message, not Commitment (see CommitmentOut's
    docstring), so this does one query for all the messages involved
    rather than querying per-commitment (avoids N+1 at even modest scale,
    while still being simple enough for demo scope — no need for a full
    join/ORM relationship here).
    """
    if not commitments:
        return []

    message_ids = [c.source_message_id for c in commitments]
    channel_by_message_id = dict(
        db.query(Message.message_id, Message.channel)
        .filter(Message.message_id.in_(message_ids))
        .all()
    )

    results = []
    for c in commitments:
        out = CommitmentOut.model_validate(c)
        out.channel = channel_by_message_id.get(c.source_message_id)
        results.append(out)
    return results


@router.post("/messages", response_model=ApiResponse)
def submit_message(payload: MessageIn, db: Session = Depends(get_db)):
    """
    The core demo endpoint: submit a message, call, or in-person
    conversation, and the full closed loop (Extraction + Lifecycle
    cross-referencing) runs against it for real.
    """
    result = process_incoming_message(db, payload.body, payload.channel)
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
    data = [c.model_dump() for c in _to_commitment_out_list(db, commitments)]
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
        at_risk_commitments=_to_commitment_out_list(db, at_risk),
        upcoming_commitments=_to_commitment_out_list(db, pending),
    )
    return ApiResponse(data=digest.model_dump())


@router.patch("/commitments/{commitment_id}", response_model=ApiResponse)
def update_commitment(
    commitment_id: str, payload: CommitmentUpdate, db: Session = Depends(get_db)
):
    """
    Manual state override — see CommitmentUpdate's docstring for why this
    exists alongside (not instead of) the AI-driven Lifecycle Tracker.

    Scoped deliberately narrow for demo purposes: only pending<->fulfilled
    transitions are allowed here (not at-risk, not arbitrary states) —
    at-risk is a derived/computed state (see refresh_deadline_states),
    not something a manual click should override, since it would just get
    recalculated back on the next read anyway.
    """
    user_id = _get_demo_user_id(db)
    commitment = (
        db.query(Commitment)
        .filter(
            Commitment.commitment_id == commitment_id,
            Commitment.user_id == user_id,
            Commitment.is_deleted.is_(False),
        )
        .first()
    )
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found")

    commitment.state = payload.state
    commitment.resolved_at = datetime.now(timezone.utc) if payload.state == "fulfilled" else None
    db.commit()
    db.refresh(commitment)

    out = _to_commitment_out_list(db, [commitment])[0]
    return ApiResponse(data=out.model_dump())
