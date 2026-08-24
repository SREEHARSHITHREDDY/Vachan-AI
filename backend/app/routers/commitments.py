"""
API routes — Stage 4 demo scope only: submit a message, list commitments,
get today's digest. Full production scope (pagination, relationship
scoring, calendar actions) is documented in docs/04_API_Design.md but not
built here — see Reconciliation Addendum Item 24 on right-sizing for a
solo demo build.

Per-user isolation update: every route now resolves the acting user via
Depends(get_current_user_id) — the real, authenticated user from the JWT
— instead of the old _get_demo_user_id(db) shared-single-user shortcut.
Each user now only ever sees, creates, or modifies their own rows.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.models.database import get_db
from app.models.db_models import Commitment, Contact, Message
from app.schemas.api import ApiResponse, CommitmentOut, CommitmentUpdate, DigestOut, MessageIn
from app.services.message_processor import process_incoming_message, refresh_deadline_states

router = APIRouter()


def _to_commitment_out_list(db: Session, commitments: list[Commitment]) -> list[CommitmentOut]:
    """
    Attaches each commitment's source channel (message/call/in-person) and
    linked contact's name — neither lives directly on Commitment (channel
    is on Message; the name is on Contact, only contact_id is on
    Commitment) — so this does one query per lookup table for all the
    commitments involved, rather than querying per-commitment (avoids N+1
    at even modest scale, while still being simple enough for demo scope).
    """
    if not commitments:
        return []

    message_ids = [c.source_message_id for c in commitments]
    channel_by_message_id = dict(
        db.query(Message.message_id, Message.channel)
        .filter(Message.message_id.in_(message_ids))
        .all()
    )

    contact_ids = [c.contact_id for c in commitments if c.contact_id]
    name_by_contact_id = {}
    if contact_ids:
        name_by_contact_id = dict(
            db.query(Contact.contact_id, Contact.name)
            .filter(Contact.contact_id.in_(contact_ids))
            .all()
        )

    results = []
    for c in commitments:
        out = CommitmentOut.model_validate(c)
        out.channel = channel_by_message_id.get(c.source_message_id)
        out.contact_id = c.contact_id
        out.contact_name = name_by_contact_id.get(c.contact_id) if c.contact_id else None
        results.append(out)
    return results


@router.post("/messages", response_model=ApiResponse)
def submit_message(
    payload: MessageIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    The core demo endpoint: submit a message, call, or in-person
    conversation, and the full closed loop (Extraction + Lifecycle
    cross-referencing) runs against it for real, scoped to the
    authenticated user only.
    """
    result = process_incoming_message(db, payload.body, user_id, payload.channel)
    return ApiResponse(data=result.model_dump())


@router.get("/commitments", response_model=ApiResponse)
def list_commitments(
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
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
def get_digest(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Read-only summary (per UI/UX doc Section 6.2 — the digest is the entry
    point, not the raw commitment list).
    """
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
    commitment_id: str,
    payload: CommitmentUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Manual override — see CommitmentUpdate's docstring for why this
    exists alongside (not instead of) the AI-driven Lifecycle Tracker,
    and why "at-risk" is now a valid manual target too, not just
    pending/fulfilled.
    """
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

    if payload.state is not None:
        commitment.state = payload.state
        commitment.resolved_at = datetime.now(timezone.utc) if payload.state == "fulfilled" else None

    if payload.inferred_deadline is not None:
        commitment.inferred_deadline = payload.inferred_deadline

    if payload.starts_at is not None:
        commitment.starts_at = payload.starts_at

    if payload.reminder_minutes_before is not None:
        if payload.reminder_minutes_before == 0:
            commitment.reminder_minutes_before = None  # explicit clear — see CommitmentUpdate docstring
        else:
            # A reminder needs a deadline to count backward from — either
            # already on the row, or being set in this same request.
            effective_deadline = payload.inferred_deadline or commitment.inferred_deadline
            if effective_deadline is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot set a reminder on a commitment with no deadline.",
                )
            commitment.reminder_minutes_before = payload.reminder_minutes_before

    if payload.contact_id is not None:
        contact = (
            db.query(Contact)
            .filter(
                Contact.contact_id == payload.contact_id,
                Contact.user_id == user_id,
                Contact.is_deleted.is_(False),
            )
            .first()
        )
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        commitment.contact_id = payload.contact_id

    db.commit()
    db.refresh(commitment)

    out = _to_commitment_out_list(db, [commitment])[0]
    return ApiResponse(data=out.model_dump())


@router.delete("/commitments/{commitment_id}", response_model=ApiResponse)
def delete_commitment(
    commitment_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Soft-delete — sets is_deleted/deleted_at (columns that already
    existed on the model since Stage 3, per the Reconciliation Addendum's
    soft-delete decision) rather than removing the row. This preserves
    history for anything that might reference it later (e.g. relationship
    scoring in a future phase), and matches how Contact soft-delete works.
    """
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

    commitment.is_deleted = True
    commitment.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return ApiResponse(data={"commitment_id": commitment_id, "deleted": True})
