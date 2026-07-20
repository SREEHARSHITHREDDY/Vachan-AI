"""
Test suite for the Commitment Extraction Service.

Two kinds of tests here, matching the Reconciliation Addendum (Item 6):
targeted coverage of the core service, not exhaustive coverage of glue code.

1. Unit tests with a mocked LLM client — fast, free, run in CI/locally
   without an API key. These test the SERVICE logic (preprocessing,
   validation, error handling), not the model's actual classification
   accuracy.

2. A live evaluation test (skipped unless GROQ_API_KEY is set) that
   runs the real labeled test set through the real model and reports
   precision — this is the Week 3-5 checkpoint from the Execution Plan
   ("measure precision/recall on the labeled test set").

Run unit tests only:      pytest tests/test_extraction_service.py -m "not live"
Run the live eval too:    pytest tests/test_extraction_service.py --run-live
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.schemas.commitment import ExtractionResult
from app.services.extraction_service import (
    ExtractionService,
    strip_signature_and_quotes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Unit tests (mocked LLM — no API key needed)
# ---------------------------------------------------------------------------


def test_strip_signature_removes_common_signoff():
    raw = "I'll send the deck by Friday.\n--\nSent from my iPhone"
    cleaned = strip_signature_and_quotes(raw)
    assert cleaned == "I'll send the deck by Friday."


def test_strip_signature_removes_quoted_reply():
    raw = "Sounds good, I'll follow up.\nOn Mon, Jane wrote:\n> original message"
    cleaned = strip_signature_and_quotes(raw)
    assert cleaned == "Sounds good, I'll follow up."


def test_strip_signature_leaves_clean_message_untouched():
    raw = "I'll send the deck by Friday."
    assert strip_signature_and_quotes(raw) == raw


def test_extract_returns_validated_result_on_well_formed_llm_response():
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "is_commitment": True,
        "commitment_type": "made-by-me",
        "description": "Send the deck by Friday",
        "inferred_deadline": None,
        "confidence": "high",
    }

    service = ExtractionService(llm_client=mock_client)
    result = service.extract("I'll send the deck by Friday.")

    assert isinstance(result, ExtractionResult)
    assert result.is_commitment is True
    assert result.commitment_type == "made-by-me"
    mock_client.get_structured_response.assert_called_once()


def test_extract_raises_on_malformed_llm_response():
    """
    Per AI Architecture 7.5: a malformed output must be rejected, not
    silently accepted. Pydantic validation is the enforcement point.
    """
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "is_commitment": "not-a-boolean",  # malformed on purpose
        "confidence": "high",
    }

    service = ExtractionService(llm_client=mock_client)
    with pytest.raises(Exception):
        service.extract("Some message")


def test_extract_handles_non_commitment_message():
    mock_client = MagicMock()
    mock_client.get_structured_response.return_value = {
        "is_commitment": False,
        "commitment_type": None,
        "description": None,
        "inferred_deadline": None,
        "confidence": "high",
    }

    service = ExtractionService(llm_client=mock_client)
    result = service.extract("Thanks for the update, noted.")

    assert result.is_commitment is False
    assert result.commitment_type is None


# ---------------------------------------------------------------------------
# Live evaluation (real API, real labeled set) — Execution Plan Week 3-5 checkpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def labeled_examples():
    with open(FIXTURES_DIR / "labeled_test_set.json") as f:
        data = json.load(f)
    return data["examples"]


def test_live_precision_against_labeled_set(request, labeled_examples):
    """
    This is the actual accuracy checkpoint from the Execution Plan
    (Weeks 3-5: "measure precision/recall on the labeled test set,
    target >80% precision" — see Database/AI Architecture docs).

    Skipped by default since it costs real API credits. Run explicitly with:
        pytest tests/test_extraction_service.py --run-live
    """
    if not request.config.getoption("--run-live"):
        pytest.skip("Live evaluation skipped — pass --run-live to run it.")

    from app.core.config import get_settings

    if not get_settings().groq_api_key:
        pytest.skip("GROQ_API_KEY not set in .env — cannot run live evaluation.")

    service = ExtractionService()  # real LLMClient, real API call

    correct = 0
    total = len(labeled_examples)
    failures = []

    for example in labeled_examples:
        result = service.extract(example["message"])
        expected = example["expected"]

        is_match = (
            result.is_commitment == expected["is_commitment"]
            and (result.commitment_type == expected["commitment_type"]
                 if expected["is_commitment"] else True)
        )
        if is_match:
            correct += 1
        else:
            failures.append(
                {
                    "message": example["message"],
                    "expected": expected,
                    "got": result.model_dump(),
                }
            )

    precision = correct / total if total else 0
    print(f"\nPrecision on labeled test set: {precision:.1%} ({correct}/{total})")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")

    assert precision >= 0.80, (
        f"Precision {precision:.1%} is below the 80% target "
        f"(Reconciliation Addendum Item 6 / AI Architecture 7.7)"
    )
