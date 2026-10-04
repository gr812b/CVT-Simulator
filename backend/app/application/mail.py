"""Password reset delivery with an explicit local-only outbox."""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from uuid import uuid4

from app.core.settings import Settings

logger = logging.getLogger(__name__)


def send_password_reset(settings: Settings, recipient: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = "Reset your CINDER password"
    # Fragment tokens stay out of HTTP access logs and referrer URLs.
    link = f"{settings.web_url}/reset-password#token={token}"
    minutes = max(1, settings.reset_lifetime_seconds // 60)
    message.set_content(
        f"Reset your CINDER password using this link within {minutes} minutes:\n\n"
        f"{link}\n\nIf you did not request this, you can ignore this email.\n"
    )
    if settings.mail_mode == "outbox":
        if settings.environment != "development":
            raise RuntimeError("The mail outbox is only available in development.")
        settings.mail_outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = settings.mail_outbox / f"{uuid4()}.eml"
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(message.as_bytes())
        return
    try:
        transport = (
            smtplib.SMTP_SSL if settings.smtp_security == "tls" else smtplib.SMTP
        )
        options = (
            {"context": ssl.create_default_context()}
            if settings.smtp_security == "tls"
            else {}
        )
        with transport(
            settings.smtp_host, settings.smtp_port, timeout=15, **options
        ) as smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        # Never log the link, token, password or recipient.
        logger.error("Password reset email delivery failed; check SMTP configuration.")
