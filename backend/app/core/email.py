"""
Email sending — currently only used for the signup verification link.

Uses Python's built-in smtplib against Gmail's SMTP server with an app
password (not the account's real password — app passwords are Google's
mechanism for letting a non-Google application authenticate on behalf of
an account that has 2FA enabled, without exposing the real credential).

Deliberately synchronous (blocking) — this is demo scope with a handful
of signups, not production email volume. A real deployment would move
this to a background task/queue rather than blocking the request while
SMTP round-trips.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings


class EmailNotConfiguredError(Exception):
    """Raised when SMTP credentials aren't set — fails loudly rather than
    silently pretending an email was sent when it wasn't."""


def send_verification_email(to_email: str, verification_link: str) -> None:
    settings = get_settings()
    if not settings.smtp_username or not settings.smtp_password:
        raise EmailNotConfiguredError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set in .env to send "
            "verification emails. See the Gmail app-password setup steps."
        )

    # Google displays app passwords with spaces for human readability
    # (e.g. "abcd efgh ijkl mnop"), but the actual credential has none —
    # stripping here means a password pasted straight from Google's page,
    # spaces and all, still works instead of silently failing auth.
    smtp_username = settings.smtp_username.strip()
    smtp_password = settings.smtp_password.replace(" ", "").strip()

    message = MIMEMultipart("alternative")
    message["Subject"] = "Verify your VachanAI account"
    message["From"] = smtp_username
    message["To"] = to_email

    text_body = (
        f"Welcome to VachanAI!\n\n"
        f"Click the link below to verify your email and activate your account:\n\n"
        f"{verification_link}\n\n"
        f"If you didn't sign up for VachanAI, you can safely ignore this email."
    )
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1A1F3A;">Welcome to VachanAI</h2>
      <p>Click the button below to verify your email and activate your account.</p>
      <p style="text-align: center; margin: 32px 0;">
        <a href="{verification_link}"
           style="background: #7c9eff; color: #fff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600;">
          Verify My Email
        </a>
      </p>
      <p style="color: #6b7280; font-size: 13px;">
        If you didn't sign up for VachanAI, you can safely ignore this email.
      </p>
    </div>
    """

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, to_email, message.as_string())
