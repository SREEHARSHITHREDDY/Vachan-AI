"""Gmail connector — IMAP is faked, so no network and no real account."""

import imaplib
from email.message import EmailMessage

import pytest

from app.services.connectors import gmail
from app.services.connectors.types import ConnectorAuthError, ConnectorError


def _raw(to="Priya Sharma <priya@example.com>", subject="Notes", body="I'll send the notes tomorrow.",
         date="Mon, 05 Jan 2026 10:00:00 +0530", message_id="<abc@mail.gmail.com>", html=None):
    m = EmailMessage()
    m["To"], m["Subject"], m["Date"], m["Message-ID"] = to, subject, date, message_id
    if html:
        m.set_content("fallback")
        m.clear_content()
        m.set_content(html, subtype="html")
    else:
        m.set_content(body)
    return m.as_bytes()


class FakeIMAP:
    """Minimal imaplib stand-in; class attributes are set per test."""

    messages: dict[bytes, bytes] = {}
    login_error = False
    folders = [b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']
    instances: list = []

    def __init__(self, host, timeout=None):
        self.host, self.selected, self.readonly = host, None, None
        self.logged_out = False
        FakeIMAP.instances.append(self)

    def login(self, user, password):
        self.creds = (user, password)
        if FakeIMAP.login_error:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def list(self):
        return "OK", FakeIMAP.folders

    def select(self, folder, readonly=False):
        self.selected, self.readonly = folder, readonly
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        self.criteria = criteria
        return "OK", [b" ".join(FakeIMAP.messages)]

    def fetch(self, msg_id, parts):
        self.fetch_parts = parts
        return "OK", [(b"1 (BODY[] {n})", FakeIMAP.messages[msg_id]), b")"]

    def logout(self):
        self.logged_out = True


@pytest.fixture(autouse=True)
def reset_fake():
    FakeIMAP.messages, FakeIMAP.login_error, FakeIMAP.instances = {}, False, []
    FakeIMAP.folders = [b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']


def test_reads_sent_mail_readonly_and_parses_fields():
    FakeIMAP.messages = {b"1": _raw()}
    msgs = gmail.read_sent_messages("me@gmail.com", "abcd efgh ijkl mnop", imap_factory=FakeIMAP)
    conn = FakeIMAP.instances[0]
    assert conn.creds == ("me@gmail.com", "abcdefghijklmnop")  # spaces stripped
    assert conn.readonly is True and "BODY.PEEK" in conn.fetch_parts
    assert conn.logged_out is True
    m = msgs[0]
    assert m.channel == "gmail" and m.external_id == "gmail:<abc@mail.gmail.com>"
    assert m.counterparty_name == "Priya Sharma" and m.counterparty_handle == "priya@example.com"
    assert m.body.startswith("Subject: Notes") and "send the notes tomorrow" in m.body
    assert m.sent_at.utcoffset().total_seconds() == 0  # normalised to UTC
    assert (m.sent_at.hour, m.sent_at.minute) == (4, 30)  # 10:00 +0530


def test_finds_localised_sent_folder_by_flag():
    FakeIMAP.folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Gesendet"']
    FakeIMAP.messages = {b"1": _raw()}
    gmail.read_sent_messages("me@gmail.com", "abcdefghijklmnop", imap_factory=FakeIMAP)
    assert FakeIMAP.instances[0].selected == '"[Gmail]/Gesendet"'


def test_html_only_email_is_converted_to_text():
    FakeIMAP.messages = {b"1": _raw(html="<html><body><p>I will <b>call</b> you</p><script>x()</script></body></html>")}
    body = gmail.read_sent_messages("me@gmail.com", "abcdefghijklmnop", imap_factory=FakeIMAP)[0].body
    assert "I will call you" in body and "x()" not in body


def test_only_most_recent_messages_returned_oldest_first():
    FakeIMAP.messages = {
        b"1": _raw(date="Mon, 05 Jan 2026 10:00:00 +0000", message_id="<1@x>"),
        b"2": _raw(date="Tue, 06 Jan 2026 10:00:00 +0000", message_id="<2@x>"),
        b"3": _raw(date="Wed, 07 Jan 2026 10:00:00 +0000", message_id="<3@x>"),
    }
    msgs = gmail.read_sent_messages("me@gmail.com", "abcdefghijklmnop", max_messages=2, imap_factory=FakeIMAP)
    assert [m.external_id for m in msgs] == ["gmail:<2@x>", "gmail:<3@x>"]


def test_bad_login_raises_auth_error_with_guidance():
    FakeIMAP.login_error = True
    with pytest.raises(ConnectorAuthError) as e:
        gmail.read_sent_messages("me@gmail.com", "wrongwrongwrong", imap_factory=FakeIMAP)
    assert "app password" in str(e.value).lower()
    assert FakeIMAP.instances[0].logged_out is True


def test_network_failure_becomes_connector_error():
    def boom(host, timeout=None):
        raise OSError("network down")
    with pytest.raises(ConnectorError):
        gmail.read_sent_messages("me@gmail.com", "abcdefghijklmnop", imap_factory=boom)


def test_email_without_usable_date_or_body_is_skipped():
    FakeIMAP.messages = {b"1": _raw(date="not a date"), b"2": _raw(body="   ")}
    assert gmail.read_sent_messages("me@gmail.com", "abcdefghijklmnop", imap_factory=FakeIMAP) == []
