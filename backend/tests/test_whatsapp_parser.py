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


# ---- everyone's messages + who each one is with --------------------------

from app.services.connectors.whatsapp import parse_chat_all  # noqa: E402

GROUP = """\
05/10/2026, 10:00 - Rahul: Harshith can we meet at 4:30 pm on 7th Oct for the demo?
05/10/2026, 10:02 - Harshith: Sure Rahul, see you then
05/10/2026, 10:10 - Priya: Can you share the dataset by Thursday?
05/10/2026, 10:11 - Harshith: Yes I will send it tomorrow
05/10/2026, 14:00 - Harshith: I will bring the printed copies on Monday
05/10/2026, 14:05 - Ankit: I'll fix the login bug by tomorrow
"""


def test_parse_all_returns_both_directions_with_sender_and_direction():
    msgs = parse_chat_all(GROUP, "Harshith", chat_name="Project Team")
    assert [(m.sender_name, m.direction) for m in msgs][:3] == [
        ("Rahul", "inbound"), ("Harshith", "outbound"), ("Priya", "inbound")]
    assert len(msgs) == 6
    assert all(m.thread_key == "project team" for m in msgs)


def test_outbound_ids_match_parse_chat_so_old_imports_still_dedupe():
    only_mine = {m.external_id for m in parse_chat(GROUP, "Harshith", chat_name="Project Team")}
    all_mine = {m.external_id for m in parse_chat_all(GROUP, "Harshith", chat_name="Project Team")
                if m.direction == "outbound"}
    assert only_mine == all_mine and all(i.startswith("wa:") for i in only_mine)
    assert all(m.external_id.startswith("wa-in:") for m in parse_chat_all(GROUP, "Harshith")
               if m.direction == "inbound")


def test_group_message_is_attributed_to_the_named_person_then_the_one_replied_to():
    msgs = {m.body[:12]: m for m in parse_chat_all(GROUP, "Harshith", chat_name="Project Team")}
    assert msgs["Sure Rahul, "].counterparty_name == "Rahul"          # named in the text
    assert msgs["Yes I will s"].counterparty_name == "Priya"          # replying to Priya
    # nobody named and the last speaker is 4 hours back → falls back to the chat
    assert msgs["I will bring"].counterparty_name == "Project Team"


def test_inbound_message_is_with_its_sender_and_one_to_one_uses_the_other_person():
    msgs = parse_chat_all(GROUP, "Harshith")
    assert [m.counterparty_name for m in msgs if m.direction == "inbound"] == ["Rahul", "Priya", "Ankit"]
    one = parse_chat_all(ANDROID_24H, "Harshith", chat_name="whatever.txt")
    assert {m.counterparty_name for m in one} == {"Priya"}


def test_chat_where_the_user_never_replied_is_all_incoming_not_an_error():
    text = ("04/10/2026, 20:15 - Sneha: Hi, I finished the poster draft\n"
            "04/10/2026, 20:16 - Sneha: Can you review it and send me feedback by Wednesday?\n")
    msgs = parse_chat_all(text, "Harshith", chat_name="Sneha")
    assert [m.direction for m in msgs] == ["inbound", "inbound"]
    assert {m.counterparty_name for m in msgs} == {"Sneha"}
    assert parse_chat(text, "Harshith") == []  # nothing of mine to analyse


def test_unknown_name_is_still_rejected_when_several_people_spoke():
    with pytest.raises(ConnectorError):
        parse_chat_all(GROUP, "Nobody")
