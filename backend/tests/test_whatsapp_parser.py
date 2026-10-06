"""WhatsApp export parser — pure parsing, no DB, no LLM."""

import pytest

from app.services.connectors.types import ConnectorError
from app.services.connectors.whatsapp import inspect_chat, parse_chat

ANDROID_24H = """\
31/12/2025, 21:40 - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.
31/12/2025, 21:41 - Priya: Can you share the notes?
31/12/2025, 21:42 - Harshith: Sure, I'll send the notes by tomorrow evening
and the slides as well
01/01/2026, 18:05 - Harshith: <Media omitted>
01/01/2026, 18:06 - Harshith: Sent the notes just now
01/01/2026, 18:07 - Priya: thanks!
"""

IOS_12H = """\
\u200e[05/01/26, 9:41:05 PM] Harshith: \u200eI will submit the report on Friday
[05/01/26, 9:42:00 PM] Ravi: great
"""


def test_android_basic_parse_and_filtering():
    msgs = parse_chat(ANDROID_24H, "Harshith")
    # media placeholder + other person's messages + system line are dropped
    assert [m.body for m in msgs] == [
        "Sure, I'll send the notes by tomorrow evening\nand the slides as well",
        "Sent the notes just now",
    ]
    assert all(m.channel == "whatsapp" for m in msgs)
    assert msgs[0].counterparty_name == "Priya"


def test_my_name_is_case_insensitive_and_unknown_name_lists_participants():
    assert parse_chat(ANDROID_24H, "harshith")
    with pytest.raises(ConnectorError) as e:
        parse_chat(ANDROID_24H, "Nobody")
    assert "Harshith" in str(e.value) and "Priya" in str(e.value)


def test_ios_format_with_invisible_marks_and_12h_clock():
    msgs = parse_chat(IOS_12H, "Harshith")
    assert len(msgs) == 1
    assert msgs[0].body == "I will submit the report on Friday"
    assert msgs[0].sent_at.hour == 21 and msgs[0].sent_at.minute == 41


def test_12h_midnight_and_noon():
    text = (
        "01/02/2026, 12:05 am - Me: starting late tonight, will finish the draft\n"
        "01/02/2026, 12:05 pm - Me: lunch done, now I will finish the draft\n"
        "01/02/2026, 1:00 pm - You: x\n"
    )
    msgs = parse_chat(text, "me")
    assert [m.sent_at.hour for m in msgs] == [0, 12]


def test_utc_offset_converts_local_time():
    ist = parse_chat(ANDROID_24H, "Harshith", utc_offset_minutes=330)
    utc = parse_chat(ANDROID_24H, "Harshith", utc_offset_minutes=0)
    assert (utc[0].sent_at - ist[0].sent_at).total_seconds() == 330 * 60


def test_date_order_detection():
    mdy = "12/31/2025, 9:41 PM - Me: I will send the file later today\n"
    assert parse_chat(mdy, "Me")[0].sent_at.month == 12  # second number >12 → month-first
    dmy = "31/12/2025, 21:41 - Me: I will send the file later today\n"
    assert parse_chat(dmy, "Me")[0].sent_at.day == 31
    ambiguous = "03/04/2025, 21:41 - Me: I will send the file later today\n"
    assert parse_chat(ambiguous, "Me")[0].sent_at.month == 4  # defaults to day-first
    assert parse_chat(ambiguous, "Me", date_order="mdy")[0].sent_at.month == 3


def test_ids_are_stable_across_reimport_and_distinct_for_duplicate_text():
    text = (
        "01/02/2026, 10:00 - Me: will do that now ok\n"
        "01/02/2026, 10:00 - Me: will do that now ok\n"
    )
    first = [m.external_id for m in parse_chat(text, "Me")]
    second = [m.external_id for m in parse_chat(text, "Me")]
    assert first == second
    assert len(set(first)) == 2


def test_group_chat_uses_chat_name_not_a_guessed_member():
    text = (
        "01/02/2026, 10:00 - Me: I will bring the charts on Monday\n"
        "01/02/2026, 10:01 - A: ok\n01/02/2026, 10:02 - B: ok\n"
    )
    assert parse_chat(text, "Me")[0].counterparty_name is None
    assert parse_chat(text, "Me", chat_name="Project Group")[0].counterparty_name == "Project Group"


def test_inspect_lists_participants_with_counts():
    info = inspect_chat(ANDROID_24H)
    names = {p["name"]: p["message_count"] for p in info["participants"]}
    assert names == {"Priya": 2, "Harshith": 2}
    assert info["total_messages"] == 4


def test_non_chat_text_is_rejected():
    with pytest.raises(ConnectorError):
        inspect_chat("this is just some random text\nwith no timestamps")


def test_ids_do_not_depend_on_the_timezone_offset_used():
    a = [m.external_id for m in parse_chat(ANDROID_24H, "Harshith", utc_offset_minutes=0)]
    b = [m.external_id for m in parse_chat(ANDROID_24H, "Harshith", utc_offset_minutes=330)]
    assert a == b
