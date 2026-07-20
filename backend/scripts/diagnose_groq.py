"""
Standalone diagnostic — bypasses ExtractionService/LLMClient entirely and
talks to Groq directly, printing the RAW response (including finish_reason
and any reasoning content). Use this if test_live_precision_against_labeled_set
fails again after the max_tokens fix, to see exactly what Groq returned
instead of guessing.

Run with:
    ./venv/bin/python scripts/diagnose_groq.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings  # noqa: E402
from groq import Groq  # noqa: E402

settings = get_settings()

if not settings.groq_api_key:
    print("GROQ_API_KEY not set in .env — cannot run this diagnostic.")
    sys.exit(1)

client = Groq(api_key=settings.groq_api_key)

print(f"Model: {settings.llm_model}")
print(f"Max tokens: {settings.extraction_max_tokens}")
print("Sending a simple test request...\n")

response = client.chat.completions.create(
    model=settings.llm_model,
    max_tokens=settings.extraction_max_tokens,
    temperature=0.0,
    messages=[
        {
            "role": "system",
            "content": (
                "Classify whether the following message is a commitment. "
                "Respond with ONLY a JSON object: "
                '{"is_commitment": true or false, "reasoning": "brief explanation"}'
            ),
        },
        {"role": "user", "content": "I'll send you the report by Friday."},
    ],
    response_format={"type": "json_object"},
)

choice = response.choices[0]
print("finish_reason:", choice.finish_reason)
print("message.content (raw):", repr(choice.message.content))

# gpt-oss models may expose reasoning separately depending on SDK version —
# print it if present, since this is exactly what we need to see if the
# max_tokens fix didn't resolve the empty-output issue.
reasoning = getattr(choice.message, "reasoning", None)
if reasoning:
    print("message.reasoning (first 500 chars):", reasoning[:500])

print("\nusage:", response.usage)
