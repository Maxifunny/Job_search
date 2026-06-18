"""SMTP email delivery."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send multipart (text + HTML) emails via SMTP."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.smtp_host
            and self.settings.smtp_from
            and self.settings.smtp_to
        )

    def recipients(self) -> list[str]:
        return [
            part.strip()
            for part in self.settings.smtp_to.split(",")
            if part.strip()
        ]

    def send(self, *, subject: str, text_body: str, html_body: str) -> list[str]:
        if not self.is_configured():
            raise RuntimeError(
                "SMTP nie jest skonfigurowane. Ustaw SMTP_HOST, SMTP_FROM i SMTP_TO w .env"
            )

        recipients = self.recipients()
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from
        message["To"] = ", ".join(recipients)
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        logger.info(
            "Sending email to %s (subject=%s)",
            ", ".join(recipients),
            subject,
        )

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_password)
            smtp.sendmail(
                self.settings.smtp_from,
                recipients,
                message.as_string(),
            )

        return recipients
