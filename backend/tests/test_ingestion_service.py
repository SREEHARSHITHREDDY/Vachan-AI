"""
Ingestion pipeline against a real in-memory DB with the LLM layer faked
(so it costs no API credits and runs without a key).
"""

from datetime import datetime, timezone

import pytest

from app.core.config import get_settings
from app.main import app
from app.models.database import get_db
from app.models.db_models import Commitment, Contact, Message, User
from app.schemas.commitment import CommitmentType, ConfidenceLevel, ExtractionResult
from app.schemas.lifecycle import ResolutionCheckResult
from app.services.connectors.types import ParsedMessage
from app.services.ingestion_service import ingest_messages
from app.services.message_processor import _get_demo_user_id


class FakeExtractor:
    calls: list = []
    fail = False

    def extract(self, body, reference_time=None):
        FakeExtractor.calls.append((body, reference_time))
        if FakeExtractor.fail:
            raise RuntimeError("llm down")
        is_c = "i'll" in body.lower() or "i will" in body.lower()
        return ExtractionResult(
            is_commitment=is_c,
            commitment_type=CommitmentType.MADE_BY_ME if is_c else None,
            description=body if is_c else None,
            confidence=ConfidenceLevel.HIGH,
        )


class FakeTracker:
    def check_for_resolution(self, body, open_commitments):
        if body.lower().startswith("sent") and open_commitments:
            return ResolutionCheckResult(
                resolved=True,
                resolved_commitment_id=open_commitments[0].commitment_id,
                reasoning="message says it was sent",
            )
        return ResolutionCheckResult(resolved=False, resolved_commitment_id=None)


@pytest.fixture
def env(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    monkeypatch.setattr("app.services.message_processor.ExtractionService", FakeExtractor)
    monkeypatch.setattr("app.services.message_processor.LifecycleTracker", FakeTracker)
    FakeExtractor.calls, FakeExtractor.fail = [], False
    db = next(app.dependency_overrides[get_db]())
    return db, _get_demo_user_id(db)


def _msg(body, day, hour=10, ext=None, name="Priya", handle=None, channel="whatsapp"):
    return ParsedMessage(
        channel=channel,
        external_id=ext or f"id-{day}-{hour}-{body[:8]}",
        body=body,
        sent_at=datetime(2026, 1, day, hour, 0, tzinfo=timezone.utc),
        counterparty_name=name,
        counterparty_handle=handle,
    )


PROMISE = _msg("Sure, I'll send the notes by tomorrow evening", 5)
DONE = _msg("Sent the notes just now", 6)


def test_processes_chronologically_even_if_given_out_of_order(env):
    db, uid = env
    summary = ingest_messages(db, uid, [DONE, PROMISE], "whatsapp")  # reversed on purpose
    assert (summary.commitments_created, summary.commitments_resolved) == (1, 1)
    c = db.query(Commitment).one()
    assert c.state == "fulfilled"
    assert c.resolved_at.replace(tzinfo=None) == DONE.sent_at.replace(tzinfo=None)  # message time, not "now"
    assert summary.items[0].new_commitment and summary.items[1].resolved_commitment_id == c.commitment_id


def test_reference_time_is_passed_to_extractor_for_imported_messages(env):
    db, uid = env
    ingest_messages(db, uid, [PROMISE], "whatsapp")
    assert FakeExtractor.calls[0][1] == PROMISE.sent_at


def test_rerunning_the_same_import_does_nothing(env):
    db, uid = env
    ingest_messages(db, uid, [PROMISE, DONE], "whatsapp")
    again = ingest_messages(db, uid, [PROMISE, DONE], "whatsapp")
    assert again.already_imported == 2 and again.processed == 0
    assert db.query(Message).count() == 2 and db.query(Commitment).count() == 1


def test_same_external_id_for_a_different_user_is_not_a_duplicate(env):
    db, uid = env
    other = User(email="other@example.com", persona_mode="student")
    db.add(other)
    db.commit()
    ingest_messages(db, uid, [PROMISE], "whatsapp")
    summary = ingest_messages(db, other.user_id, [PROMISE], "whatsapp")
    assert summary.already_imported == 0 and summary.commitments_created == 1


def test_contact_is_created_linked_and_reused(env):
    db, uid = env
    first = ingest_messages(db, uid, [PROMISE], "whatsapp")
    second = ingest_messages(db, uid, [_msg("I will review the draft tonight", 7)], "whatsapp")
    assert first.contacts_created == 1 and second.contacts_created == 0
    contact = db.query(Contact).filter_by(name="Priya").one()
    assert {c.contact_id for c in db.query(Commitment).all()} == {contact.contact_id}
    assert all(m.contact_id == contact.contact_id for m in db.query(Message).all())


def test_existing_contact_matched_by_email_handle(env):
    db, uid = env
    existing = Contact(user_id=uid, name="Dr. Rao", email_or_handle="rao@univ.edu", role_tag="other")
    db.add(existing)
    db.commit()
    msg = _msg("I'll upload the final report by Monday", 5, name="R", handle="RAO@univ.edu", channel="gmail")
    summary = ingest_messages(db, uid, [msg], "gmail")
    assert summary.contacts_created == 0
    assert db.query(Commitment).one().contact_id == existing.contact_id


def test_trivial_messages_are_skipped_and_not_stored(env):
    db, uid = env
    summary = ingest_messages(db, uid, [_msg("ok thanks", 5)], "whatsapp")
    assert summary.skipped_trivial == 1 and db.query(Message).count() == 0


def test_failed_llm_call_leaves_message_retryable(env):
    db, uid = env
    FakeExtractor.fail = True
    broken = ingest_messages(db, uid, [PROMISE], "whatsapp")
    assert len(broken.errors) == 1 and db.query(Message).count() == 0
    FakeExtractor.fail = False
    retry = ingest_messages(db, uid, [PROMISE], "whatsapp")
    assert retry.processed == 1 and retry.commitments_created == 1


def test_aborts_after_consecutive_failures(env):
    db, uid = env
    FakeExtractor.fail = True
    msgs = [_msg(f"I will do task number {i} soon", 5 + i, ext=f"e{i}") for i in range(6)]
    summary = ingest_messages(db, uid, msgs, "whatsapp")
    assert summary.aborted is True and len(summary.errors) == 3
    assert "I will do task" not in " ".join(summary.errors)  # message text never leaks into errors


def test_cap_keeps_most_recent_new_messages(env):
    db, uid = env
    msgs = [_msg(f"I will do task number {i} soon", 5 + i, ext=f"e{i}") for i in range(4)]
    summary = ingest_messages(db, uid, msgs, "whatsapp", max_messages=2)
    assert summary.processed == 2
    assert {m.external_id for m in db.query(Message).all()} == {"e2", "e3"}
    # a second run walks further back instead of re-picking the same tail
    nxt = ingest_messages(db, uid, msgs, "whatsapp", max_messages=2)
    assert nxt.already_imported == 2 and nxt.processed == 2
