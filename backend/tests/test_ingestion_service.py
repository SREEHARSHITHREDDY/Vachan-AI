"""
Ingestion pipeline against a real in-memory DB with the LLM layer faked
(so it costs no API credits and runs without a key).

The fakes only model the PLUMBING the real model relies on — that the
conversation context, author and local reference time actually reach the
extractor, and that resolution is scoped per person/direction. How well the
real model reads a conversation can't be tested without it.
"""

from datetime import datetime, timedelta, timezone

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

MEETING = datetime(2026, 10, 7, 16, 30)


class FakeExtractor:
    calls: list = []
    fail = False

    def extract(self, body, reference_time=None, context=None):
        FakeExtractor.calls.append({"body": body, "reference_time": reference_time, "context": context})
        if FakeExtractor.fail:
            raise RuntimeError("llm down")
        low = body.lower()
        by_other = bool(context) and "written by the user" not in context
        mk = lambda **kw: ExtractionResult(confidence=ConfidenceLevel.HIGH, **kw)  # noqa: E731

        # A bare "Sure" only means something if the chat says what it agrees to.
        if low.startswith("sure") and context and "4:30" in context:
            return mk(is_commitment=True, commitment_type=CommitmentType.MADE_BY_ME,
                      description="Meet Rahul at 4:30 PM on 7 Oct", inferred_deadline=MEETING)
        if low.startswith("can we meet"):  # a proposal from the other person
            return mk(is_commitment=True, commitment_type=CommitmentType.CONDITIONAL,
                      description="Meeting proposed", inferred_deadline=MEETING)
        if "i'll" in low or "i will" in low:
            ctype = CommitmentType.MADE_TO_ME if by_other else CommitmentType.MADE_BY_ME
            return mk(is_commitment=True, commitment_type=ctype, description=body)
        return mk(is_commitment=False)


class FakeTracker:
    calls: list = []

    def check_for_resolution(self, body, open_commitments):
        FakeTracker.calls.append((body, [str(c.commitment_id) for c in open_commitments]))
        if body.lower().startswith(("sent", "fixed", "done")) and open_commitments:
            return ResolutionCheckResult(
                resolved=True,
                resolved_commitment_id=open_commitments[0].commitment_id,
                reasoning="message says it was done",
            )
        return ResolutionCheckResult(resolved=False, resolved_commitment_id=None)


@pytest.fixture
def env(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    monkeypatch.setattr("app.services.message_processor.ExtractionService", FakeExtractor)
    monkeypatch.setattr("app.services.message_processor.LifecycleTracker", FakeTracker)
    FakeExtractor.calls, FakeExtractor.fail, FakeTracker.calls = [], False, []
    db = next(app.dependency_overrides[get_db]())
    return db, _get_demo_user_id(db)


def _msg(body, day, hour=10, ext=None, name="Priya", handle=None, channel="whatsapp",
         direction="outbound", sender=None, thread="chat-priya", minute=0):
    return ParsedMessage(
        channel=channel,
        external_id=ext or f"id-{direction}-{day}-{hour}-{minute}-{body[:8]}",
        body=body,
        sent_at=datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc),
        counterparty_name=name,
        counterparty_handle=handle,
        direction=direction,
        sender_name=sender or ("Harshith" if direction == "outbound" else name),
        thread_key=thread,
    )


PROMISE = _msg("Sure, I'll send the notes by tomorrow evening", 5)
DONE = _msg("Sent the notes just now", 6)


# ---------------------------------------------------------------- basics

def test_processes_chronologically_even_if_given_out_of_order(env):
    db, uid = env
    summary = ingest_messages(db, uid, [DONE, PROMISE], "whatsapp")  # reversed on purpose
    assert (summary.commitments_created, summary.commitments_resolved) == (1, 1)
    c = db.query(Commitment).one()
    assert c.state == "fulfilled"
    assert c.resolved_at.replace(tzinfo=None) == DONE.sent_at.replace(tzinfo=None)  # message time, not "now"
    assert summary.items[0].new_commitment and summary.items[1].resolved_commitment_id == c.commitment_id


def test_extractor_gets_the_users_local_send_time(env):
    db, uid = env
    ingest_messages(db, uid, [PROMISE], "whatsapp", utc_offset_minutes=330)
    ref = FakeExtractor.calls[0]["reference_time"]
    assert ref.tzinfo is None and ref == PROMISE.sent_at.replace(tzinfo=None) + timedelta(minutes=330)


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
    nxt = ingest_messages(db, uid, msgs, "whatsapp", max_messages=2)
    assert nxt.already_imported == 2 and nxt.processed == 2


# ------------------------------------------------------- contacts / people

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


def test_unique_first_name_matches_existing_full_name_contact(env):
    db, uid = env
    existing = Contact(user_id=uid, name="Rahul Sharma", email_or_handle="rahul@x.com", role_tag="friend")
    db.add(existing)
    db.commit()
    summary = ingest_messages(db, uid, [_msg("I will send the file tonight ok", 5, name="Rahul")], "whatsapp")
    assert summary.contacts_created == 0
    assert db.query(Commitment).one().contact_id == existing.contact_id


def test_ambiguous_first_name_is_not_guessed(env):
    db, uid = env
    for last in ("Sharma", "Verma"):
        db.add(Contact(user_id=uid, name=f"Rahul {last}", email_or_handle=f"r{last}@x.com", role_tag="other"))
    db.commit()
    summary = ingest_messages(db, uid, [_msg("I will send the file tonight ok", 5, name="Rahul")], "whatsapp")
    assert summary.contacts_created == 1
    assert db.query(Contact).filter_by(name="Rahul").count() == 1


# ----------------------------------------------- conversation understanding

def test_reply_is_read_with_its_conversation_and_named_after_the_person(env):
    db, uid = env
    ask = _msg("Can we meet at 4:30 pm on 7th Oct to go over the demo?", 5, hour=14, name="Rahul",
               direction="inbound", thread="chat-rahul")
    yes = _msg("Sure, see you then", 5, hour=14, minute=5, name="Rahul", thread="chat-rahul")
    summary = ingest_messages(db, uid, [ask, yes], "whatsapp", include_incoming=False)

    c = db.query(Commitment).one()
    assert c.description == "Meet Rahul at 4:30 PM on 7 Oct" and c.inferred_deadline == MEETING
    assert db.query(Contact).filter_by(contact_id=c.contact_id).one().name == "Rahul"
    assert "Rahul (" in FakeExtractor.calls[0]["context"] and "4:30" in FakeExtractor.calls[0]["context"]
    # include_incoming=False: Rahul's message was used as context but NOT stored
    assert db.query(Message).count() == 1
    assert summary.by_person[0].contact_name == "Rahul" and summary.by_person[0].commitments_created == 1
    assert summary.items[0].from_name == "You" and summary.items[0].contact_name == "Rahul"


def test_context_only_comes_from_the_same_chat(env):
    db, uid = env
    other_chat = _msg("Secret plan with Ankit: bring the 4:30 slides", 5, hour=9, name="Ankit",
                      direction="inbound", thread="chat-ankit")
    mine = _msg("Sure, see you then", 5, hour=10, name="Rahul", thread="chat-rahul")
    ingest_messages(db, uid, [other_chat, mine], "whatsapp")
    assert "Ankit" not in FakeExtractor.calls[-1]["context"]
    assert FakeExtractor.calls[-1]["context"].count("(no earlier messages)") == 1


def test_both_sides_mentioning_the_same_meeting_creates_one_commitment(env):
    db, uid = env
    ask = _msg("Can we meet at 4:30 pm on 7th Oct?", 5, hour=14, name="Rahul", direction="inbound", thread="t")
    yes = _msg("Sure, see you then", 5, hour=14, minute=5, name="Rahul", thread="t")
    again = _msg("Sure, 4:30 works for me", 5, hour=15, name="Rahul", thread="t")
    summary = ingest_messages(db, uid, [ask, yes, again], "whatsapp", include_incoming=True)
    assert db.query(Commitment).count() == 1 and summary.duplicates_skipped == 1


# ------------------------------------------------------ incoming messages

def test_what_others_promise_is_tracked_and_fulfilled_by_their_own_message(env):
    db, uid = env
    promise = _msg("I'll fix the login bug by tomorrow", 5, name="Ankit", direction="inbound", thread="t-ankit")
    fixed = _msg("Fixed the login bug, pushed to main", 6, name="Ankit", direction="inbound", thread="t-ankit")
    summary = ingest_messages(db, uid, [promise, fixed], "whatsapp", include_incoming=True)
    c = db.query(Commitment).one()
    assert c.commitment_type == "made-to-me" and c.state == "fulfilled"
    assert db.query(Contact).filter_by(contact_id=c.contact_id).one().name == "Ankit"
    assert summary.incoming_processed == 2
    assert {m.direction for m in db.query(Message).all()} == {"inbound"}


def test_a_proposal_from_someone_else_is_not_a_commitment_until_you_agree(env):
    db, uid = env
    ask = _msg("Can we meet at 4:30 pm on 7th Oct?", 5, name="Rahul", direction="inbound", thread="t")
    ingest_messages(db, uid, [ask], "whatsapp", include_incoming=True)
    assert db.query(Commitment).count() == 0 and db.query(Message).count() == 1


def test_resolution_is_scoped_to_the_same_person_and_direction(env):
    db, uid = env
    to_rahul = _msg("I will send Rahul the report tonight", 5, name="Rahul", thread="t-rahul")
    from_ankit = _msg("I'll fix the login bug by tomorrow", 5, hour=11, name="Ankit", direction="inbound", thread="t-ankit")
    ingest_messages(db, uid, [to_rahul, from_ankit], "whatsapp", include_incoming=True)
    rahul_id = db.query(Commitment).filter(Commitment.commitment_type == "made-by-me").one().commitment_id
    ankit_id = db.query(Commitment).filter(Commitment.commitment_type == "made-to-me").one().commitment_id

    FakeTracker.calls.clear()
    priya_done = _msg("Sent the slides to Priya", 6, name="Priya", thread="t-priya")
    ankit_done = _msg("Fixed the login bug", 6, hour=12, name="Ankit", direction="inbound", thread="t-ankit")
    ingest_messages(db, uid, [priya_done, ankit_done], "whatsapp", include_incoming=True)

    by_body = {body: ids for body, ids in FakeTracker.calls}
    # Priya has nothing open with me, so her message is never even checked
    # (no LLM call) — and in particular never against Ankit's or Rahul's promises
    assert "Sent the slides to Priya" not in by_body
    # Ankit's message may only be checked against promises made TO me, by him
    assert by_body["Fixed the login bug"] == [ankit_id]
    assert db.query(Commitment).filter_by(commitment_id=ankit_id).one().state == "fulfilled"
    assert rahul_id not in by_body["Fixed the login bug"]


# --------------------------------------------------- "get back to them"

def test_lists_chats_where_someone_is_waiting_for_your_reply(env):
    db, uid = env
    waiting = _msg("Can you review my slides and let me know?", 5, name="Sneha", direction="inbound", thread="t-sneha")
    answered = [
        _msg("Can you share the dataset please?", 5, name="Priya", direction="inbound", thread="t-priya"),
        _msg("Yes, will do that now", 5, hour=11, name="Priya", thread="t-priya"),
    ]
    thanks = _msg("Thanks a lot for the help yesterday", 5, name="Ankit", direction="inbound", thread="t-ankit")
    summary = ingest_messages(db, uid, [waiting, *answered, thanks], "whatsapp")
    assert [(a.contact_name, "slides" in a.preview) for a in summary.awaiting_reply] == [("Sneha", True)]
