"""
Contacts API routes — Phase 1 feature.

The Contact table has existed since Stage 3 (Commitment.contact_id has
always pointed here), but had no CRUD surface until now. Follows the
exact same patterns as commitments.py: demo-scope single user, soft-delete
via is_deleted/deleted_at (Reconciliation Addendum Item 5), set-only PATCH
semantics (only provided fields update).

importance_weight is intentionally NOT exposed here — it's a
Relationship-Scoring input (Database Design doc Section 4.3) that belongs
to a later phase's scoring logic, which doesn't exist yet. Exposing a
control with no consumer would be exactly the premature-building pattern
the Reconciliation Addendum warns against; it stays at its model default
(0.50) until that phase actually reads it.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.db_models import Contact
from app.schemas.api import ApiResponse, ContactCreate, ContactOut, ContactUpdate
from app.services.message_processor import _get_demo_user_id

router = APIRouter()


@router.get("/contacts", response_model=ApiResponse)
def list_contacts(db: Session = Depends(get_db)):
    user_id = _get_demo_user_id(db)
    contacts = (
        db.query(Contact)
        .filter(Contact.user_id == user_id, Contact.is_deleted.is_(False))
        .order_by(Contact.name.asc())
        .all()
    )
    data = [ContactOut.model_validate(c).model_dump() for c in contacts]
    return ApiResponse(data=data)


@router.post("/contacts", response_model=ApiResponse)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    user_id = _get_demo_user_id(db)
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
def update_contact(contact_id: str, payload: ContactUpdate, db: Session = Depends(get_db)):
    user_id = _get_demo_user_id(db)
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
def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    """
    Soft-delete only, matching Commitment. Deliberately does NOT touch
    commitments already linked to this contact via contact_id — a
    commitment's history shouldn't disappear or dangle just because the
    contact behind it was later removed; the FK simply points at a
    now-hidden contact, same as it would in any real relational system
    without a hard delete.
    """
    user_id = _get_demo_user_id(db)
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
