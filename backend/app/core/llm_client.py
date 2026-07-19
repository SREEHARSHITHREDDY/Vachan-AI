"""
Thin wrapper around the Groq API (OpenAI-compatible chat completions).

Switched from Anthropic to Groq for the 8-day demo scope — free tier and
fast API key access, versus Anthropic's billing-gated key setup, mattered
more than model choice at this stage. See ADR log for the full reasoning.

Kept deliberately minimal per AI Architecture doc Section 7.2 (few-shot
prompting, not fine-tuning) — this is not a general-purpose LLM gateway,
just the one call shape the Extraction Service needs: send a system
prompt + user content, get back raw text, let the caller parse/validate it.

Isolating this in one module also means Touchpoint 3 (sentiment scoring,
per AI Architecture Section 7.6) can later swap in a cheaper model here
without touching the Extraction Service's logic at all — and means
swapping providers again later (back to Anthropic/OpenAI, or a different
Groq model) only touches this one file.
"""

import json
from typing import Any

from groq import Groq

from app.core.config import get_settings


class LLMClient:
    """Wraps Groq's OpenAI-compatible chat completions API for structured-output calls."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = settings.llm_model
        self._max_tokens = settings.extraction_max_tokens
        self._temperature = settings.extraction_temperature

    def get_structured_response(self, system_prompt: str, user_content: str) -> dict[str, Any]:
        """
        Calls the LLM and parses the response as JSON.

        Raises ValueError if the model doesn't return valid JSON — per the
        AI Architecture doc's validation guardrail (Section 7.5), a
        malformed output is rejected here rather than passed further down
        the pipeline.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        raw_text = response.choices[0].message.content.strip()

        # Models occasionally wrap JSON in markdown code fences despite
        # instructions not to — strip defensively rather than fail on it.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM did not return valid JSON. Raw response: {raw_text!r}"
            ) from exc
