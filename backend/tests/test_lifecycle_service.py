"""
Test suite for the Lifecycle Tracker (Stage 2).

Same pattern as test_extraction_service.py: mocked-LLM unit tests for the
service logic (fast, free, no API key needed) plus one deadline-proximity
test suite that needs no LLM at all (pure date arithmetic).

There is deliberately no "live" test here yet, unlike extraction — a
meaningful live evaluation of cross-referencing needs realistic multi-thread
message scenarios, which is exactly what Week 8's checkpoint
(Execution Plan) calls for once there's real pilot data. For the 8-day demo
scope, mocked tests are sufficient to prove the mechanism is implemented
correctly.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.lifecycle import OpenCommitmentSummary, ResolutionCheckResult
from app.services.lifecycle_service import (
    LifecycleTracker,
    check_deadline_proximity,
)
from app.schemas.commitment import CommitmentState


# ---------------------------------------------------------------------------
# Deadline proximity — pure date arithmetic, no mocking needed
# ---------------------------------------------------------------------------


def test_deadline_far_away_stays_pending():
    commitment_id = uuid4()
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    deadline = now + timedelta(days=5)

    result = check_deadline_proximity(commitment_id, deadline, now=now)

    assert result.new_state == CommitmentState.PENDING


def test_deadline_within_threshold_becomes_at_risk():
    commitment_id = uuid4()
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    deadline = now + timedelta(hours=10)  # within the 24h threshold

    result = check_deadline_proximity(commitment_id, deadline, now=now)

    assert result.new_state == CommitmentState.AT_RISK


def test_no_deadline_stays_pending_indefinitely():
    commitment_id = uuid4()
    result = check_deadline_proximity(commitment_id, inferred_deadline=None)

    assert result.new_state == CommitmentState.PENDING
    assert result.hours_until_deadline is None


# ---------------------------------------------------------------------------
# Cross-referencing resolution check — mocked LLM
# ---------------------------------------------------------------------------


def _make_open_commitment(description="Send the deck by Friday"):
    return OpenCommitmentSummary(commitment_id=uuid4(), description=description)


def test_no_open_commitments_short_circuits_without_llm_call():
    """Cost/latency optimization: zero open commitments means zero LLM calls."""
    mock_client = MagicMock()
    tracker = LifecycleTracker(llm_client=mock_client)

    result = tracker.check_for_resolution("Some message", open_commitments=[])

    assert result.resolved is False
    mock_client.get_structured_response.assert_not_called()


def test_resolution_detected_from_different_thread():
    """
    THE core mechanism test: a message that resolves a commitment made in a
    completely different conversation. Per the Phase 5 SDD checkpoint, this
    exact scenario is the single most important thing to get right.
    """
    open_commitment = _make_open_commitment("Send the project deck by Friday")
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "resolved": True,
        "resolved_commitment_id": str(open_commitment.commitment_id),
        "reasoning": "The user confirmed the deck was sent.",
    }

    tracker = LifecycleTracker(llm_client=mock_client)
    result = tracker.check_for_resolution(
        "Just sent over the deck, let me know if you need anything else!",
        open_commitments=[open_commitment],
    )

    assert result.resolved is True
    assert result.resolved_commitment_id == open_commitment.commitment_id


def test_unrelated_message_does_not_resolve():
    open_commitment = _make_open_commitment()
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "resolved": False,
        "resolved_commitment_id": None,
        "reasoning": "Message is unrelated to any open commitment.",
    }

    tracker = LifecycleTracker(llm_client=mock_client)
    result = tracker.check_for_resolution(
        "What time is the meeting tomorrow?", open_commitments=[open_commitment]
    )

    assert result.resolved is False
    assert result.resolved_commitment_id is None


def test_fabricated_commitment_id_is_rejected():
    """
    Validation guardrail test: if the LLM hallucinates a commitment ID that
    wasn't in the set we gave it, the service must reject the result rather
    than silently trust it (AI Architecture 7.5 guardrail, applied here).
    """
    open_commitment = _make_open_commitment()
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "resolved": True,
        "resolved_commitment_id": str(uuid4()),  # NOT the real open commitment's ID
        "reasoning": "Fabricated.",
    }

    tracker = LifecycleTracker(llm_client=mock_client)

    with pytest.raises(ValueError, match="not in the set of open commitments"):
        tracker.check_for_resolution("Some message", open_commitments=[open_commitment])
