"""
Contacts API routes — Phase 1 feature.

Per-user isolation update: every route now resolves the acting user via
Depends(get_current_user_id) instead of the old shared _get_demo_user_id
shortcut — each user only ever sees, creates, or modifies their own
contacts now.

importance_weight is intentionally NOT exposed here — it's a
Relationship-Scoring input (Database Design doc Section 4.3) that belongs
to a later phase's scoring logic, which doesn't exist yet.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.models.database import get_db
from app.models.db_models import Commitment, Contact
from app.schemas.api import ApiResponse, ContactCreate, ContactOut, ContactUpdate

router = APIRouter()


@router.get("/contacts", response_model=ApiResponse)
def list_contacts(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    contacts = (
        db.query(Contact)
        .filter(Contact.user_id == user_id, Contact.is_deleted.is_(False))
        .order_by(Contact.name.asc())
        .all()
    )
    stats = _commitment_stats(db, user_id)
    data = []
    for c in contacts:
        out = ContactOut.model_validate(c)
        open_n, done_n, next_dl = stats.get(c.contact_id, (0, 0, None))
        out.open_commitments, out.fulfilled_commitments, out.next_deadline = open_n, done_n, next_dl
        data.append(out.model_dump())
    return ApiResponse(data=data)


def _commitment_stats(db: Session, user_id: str) -> dict:
    """contact_id -> (open count, fulfilled count, soonest open deadline),
    in ONE grouped query rather than one per contact."""
    open_states = ("pending", "at-risk")
    rows = (
        db.query(
            Commitment.contact_id,
            func.sum(case((Commitment.state.in_(open_states), 1), else_=0)),
            func.sum(case((Commitment.state == "fulfilled", 1), else_=0)),
            func.min(case((Commitment.state.in_(open_states), Commitment.inferred_deadline), else_=None)),
        )
        .filter(
            Commitment.user_id == user_id,
            Commitment.is_deleted.is_(False),
            Commitment.contact_id.isnot(None),
        )
        .group_by(Commitment.contact_id)
        .all()
    )
    stats = {}
    for contact_id, open_n, done_n, next_dl in rows:
        if isinstance(next_dl, str):  # SQLite returns the raw string from min()
            next_dl = datetime.fromisoformat(next_dl)
        stats[contact_id] = (int(open_n or 0), int(done_n or 0), next_dl)
    return stats


@router.get("/contacts/{contact_id}/commitments", response_model=ApiResponse)
def list_contact_commitments(
    contact_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Everything tied to one person, open items first (soonest deadline first)."""
    # Imported here: routers.commitments already imports from this layer's
    # siblings, and a module-level import would make the two routers depend
    # on each other at import time.
    from app.routers.commitments import _to_commitment_out_list

    contact = (
        db.query(Contact)
        .filter(
            Contact.contact_id == contact_id,
            Contact.user_id == user_id,
            Contact.is_deleted.is_(False),
        )
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    commitments = (
        db.query(Commitment)
        .filter(
            Commitment.user_id == user_id,
            Commitment.contact_id == contact_id,
            Commitment.is_deleted.is_(False),
        )
        .all()
    )
    open_first = sorted(
        commitments,
        key=lambda c: (
            c.state not in ("pending", "at-risk"),
            c.inferred_deadline is None,
            c.inferred_deadline or c.created_at,
        ),
    )
    return ApiResponse(data=[c.model_dump() for c in _to_commitment_out_list(db, open_first)])


@router.post("/contacts", response_model=ApiResponse)
def create_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    contact = Contact(
        user_id=user_id,
        name=payload.name,
        email_or_handle=payload.email_or_handle,
        role_tag=payload.role_tag,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return ApiResponse(data=ContactOut.model_validate(contact).model_dump())


@router.patch("/contacts/{contact_id}", response_model=ApiResponse)
def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    contact = (
        db.query(Contact)
        .filter(
            Contact.contact_id == contact_id,
            Contact.user_id == user_id,
            Contact.is_deleted.is_(False),
        )
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    if payload.name is not None:
        contact.name = payload.name
    if payload.email_or_handle is not None:
        contact.email_or_handle = payload.email_or_handle
    if payload.role_tag is not None:
        contact.role_tag = payload.role_tag

    db.commit()
    db.refresh(contact)
    return ApiResponse(data=ContactOut.model_validate(contact).model_dump())


@router.delete("/contacts/{contact_id}", response_model=ApiResponse)
def delete_contact(
    contact_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Soft-delete only, matching Commitment. Deliberately does NOT touch
    commitments already linked to this contact via contact_id — a
    commitment's history shouldn't disappear or dangle just because the
    contact behind it was later removed.
    """
    contact = (
        db.query(Contact)
        .filter(
            Contact.contact_id == contact_id,
            Contact.user_id == user_id,
            Contact.is_deleted.is_(False),
        )
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.is_deleted = True
    contact.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return ApiResponse(data={"contact_id": contact_id, "deleted": True})
