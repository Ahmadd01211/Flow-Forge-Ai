import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.errors import fail
from app.modules.identity.mail import enqueue
from app.modules.identity.models import AccountToken, User, UserSession
from app.modules.identity.service import token_hash


def issue(db, user, purpose, settings):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    now = datetime.now(UTC)
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    db.add(
        AccountToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=token_hash(raw),
            expires_at=now + timedelta(hours=24 if purpose == "verify" else 1),
        )
    )
    path = "verify-email" if purpose == "verify" else "reset-password"
    enqueue(
        db,
        settings,
        user.id,
        user.email,
        "Verify your email" if purpose == "verify" else "Reset your password",
        f"Open this link to continue:\n{settings.public_origin}/{path}#{raw}\n\nIf you did not request this, ignore this message.",
    )


def consume(db, raw, purpose):
    # Lock the user first to serialize token issuance and consumption.
    candidate = db.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == token_hash(raw), AccountToken.purpose == purpose
        )
    )
    if not candidate:
        fail(400, "TOKEN_INVALID", "This link has expired or was already used.")
    user = db.scalar(
        select(User)
        .where(User.id == candidate.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    token = db.scalar(
        select(AccountToken)
        .where(AccountToken.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if token.used_at or token.expires_at <= datetime.now(UTC):
        fail(400, "TOKEN_INVALID", "This link has expired or was already used.")
    token.used_at = datetime.now(UTC)
    return user


def revoke_sessions(db, user_id):
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
