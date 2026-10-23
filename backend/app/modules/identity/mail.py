"""Encrypted transactional outbox. SMTP delivery may duplicate after a crash; tokens remain single-use."""

import json
import logging
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.modules.identity.models import EmailDelivery

log = logging.getLogger("flowforge.mail")


def enqueue(db, settings, user_id, recipient, subject, text):
    message_id = uuid.uuid4()
    nonce, ciphertext = encrypt_secret(
        load_master_key(settings.credential_key_path),
        user_id,
        message_id,
        1,
        json.dumps({"to": recipient, "subject": subject, "text": text}),
    )
    db.add(EmailDelivery(id=message_id, user_id=user_id, nonce=nonce, ciphertext=ciphertext))


def deliver_pending(db, settings, send=None):
    rows = db.scalars(
        select(EmailDelivery)
        .where(
            EmailDelivery.sent_at.is_(None),
            EmailDelivery.attempts < 5,
            EmailDelivery.next_attempt_at <= datetime.now(UTC),
        )
        .limit(5)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.attempts += 1
        try:
            data = json.loads(
                decrypt_secret(
                    load_master_key(settings.credential_key_path),
                    row.user_id,
                    row.id,
                    1,
                    row.nonce,
                    row.ciphertext,
                )
            )
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = (
                settings.mail_from,
                data["to"],
                data["subject"],
            )
            message.set_content(data["text"])
            if send:
                send(message)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
                    if settings.smtp_starttls:
                        smtp.starttls()
                    if settings.smtp_username:
                        if not settings.smtp_starttls:
                            raise smtplib.SMTPException("Authenticated SMTP requires STARTTLS")
                        smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
            row.sent_at = datetime.now(UTC)
        except Exception as exc:
            row.next_attempt_at = datetime.now(UTC) + timedelta(minutes=2**row.attempts)
            log.warning("mail_delivery_failed id=%s type=%s", row.id, type(exc).__name__)
    db.commit()
