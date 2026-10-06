"""
Connector routes — read messages from Gmail or a WhatsApp chat export and
feed them through the commitment pipeline.

All routes are authenticated and scoped to the calling user. Gmail
credentials arrive in the request body, are used for that single call, and
are never stored or logged (see app/services/connectors/gmail.py).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user_id
from app.models.database import get_db
from app.models.db_models import Message
from app.schemas.api import ApiResponse
from app.schemas.connectors import (
    GmailSyncRequest,
    WhatsAppImportRequest,
    WhatsAppInspectRequest,
)
from app.services.connectors import gmail, whatsapp
from app.services.connectors.types import ConnectorAuthError, ConnectorError
from app.services.ingestion_service import ingest_messages

router = APIRouter(prefix="/connectors")


def _require_llm_key() -> None:
    # Without a key the pipeline would store messages but silently extract
    # nothing, which looks like "your chat has no promises". Fail loudly.
    if not get_settings().groq_api_key:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured on the server, so commitments can't be extracted.",
        )


@router.post("/whatsapp/inspect", response_model=ApiResponse)
def whatsapp_inspect(payload: WhatsAppInspectRequest, user_id: str = Depends(get_current_user_id)):
    """Step 1 of a WhatsApp import: who is in this chat? (no LLM, nothing stored)"""
    try:
        return ApiResponse(data=whatsapp.inspect_chat(payload.text, payload.date_order))
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/whatsapp/import", response_model=ApiResponse)
def whatsapp_import(
    payload: WhatsAppImportRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _require_llm_key()
    try:
        parsed = whatsapp.parse_chat_all(
            payload.text,
            my_name=payload.my_name,
            chat_name=payload.chat_name,
            date_order=payload.date_order,
            utc_offset_minutes=payload.utc_offset_minutes,
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    summary = ingest_messages(
        db, user_id, parsed, "whatsapp", payload.max_messages,
        include_incoming=payload.include_incoming,
        utc_offset_minutes=payload.utc_offset_minutes,
    )
    return ApiResponse(data=summary.model_dump())


@router.post("/gmail/sync", response_model=ApiResponse)
def gmail_sync(
    payload: GmailSyncRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _require_llm_key()
    password = payload.app_password.get_secret_value()
    if not 8 <= len(password.replace(" ", "")) <= 64:
        raise HTTPException(
            status_code=422,
            detail="That doesn't look like a Gmail app password (it is 16 characters).",
        )
    try:
        parsed = gmail.read_sent_messages(
            payload.gmail_address,
            password,
            since_days=payload.days,
            max_messages=payload.max_messages,
        )
    except ConnectorAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ConnectorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    summary = ingest_messages(
        db, user_id, parsed, "gmail", payload.max_messages,
        utc_offset_minutes=payload.utc_offset_minutes,
    )
    return ApiResponse(data=summary.model_dump())


@router.get("/status", response_model=ApiResponse)
def connector_status(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    """How much has each connector brought in so far (for the Connect page)."""
    rows = (
        db.query(Message.channel, func.count(Message.message_id), func.max(Message.ingested_at))
        .filter(Message.user_id == user_id, Message.external_id.isnot(None))
        .group_by(Message.channel)
        .all()
    )
    data = {"gmail": {"messages": 0, "last_synced_at": None},
            "whatsapp": {"messages": 0, "last_synced_at": None}}
    for channel, count, last in rows:
        if channel in data:
            data[channel] = {"messages": count, "last_synced_at": last.isoformat() if last else None}
    return ApiResponse(data=data)
