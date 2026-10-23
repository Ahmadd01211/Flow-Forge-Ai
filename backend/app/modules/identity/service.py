import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import fail
from app.modules.identity.models import User, UserSession

hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(raw: str, settings: Settings) -> str:
    return hmac.new(settings.session_signing_key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def check_csrf(request: Request) -> None:
    settings = request.app.state.settings
    if request.headers.get("origin") != settings.public_origin:
        fail(403, "ORIGIN_DENIED", "This request origin is not allowed.")
    raw = request.cookies.get(settings.session_cookie) or request.cookies.get(
        settings.preauth_cookie
    )
    supplied = request.headers.get("x-csrf-token", "")
    if not raw or not hmac.compare_digest(supplied, csrf_token(raw, settings)):
        fail(403, "CSRF_INVALID", "Refresh the page and try again.")


def cookie(response: Response, settings: Settings, name: str, raw: str, age: int) -> None:
    response.set_cookie(
        name,
        raw,
        max_age=age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def create_session(db: Session, user: User, response: Response, settings: Settings) -> str:
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash(raw),
            idle_expires_at=now + timedelta(hours=settings.session_idle_hours),
            absolute_expires_at=now + timedelta(hours=settings.session_absolute_hours),
        )
    )
    cookie(response, settings, settings.session_cookie, raw, settings.session_absolute_hours * 3600)
    response.delete_cookie(
        settings.preauth_cookie,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return raw


def current_session(
    request: Request, db: Session, commit_idle: bool = True
) -> tuple[User, UserSession]:
    settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie, "")
    record = (
        db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
        if raw
        else None
    )
    now = datetime.now(UTC)
    if (
        not record
        or record.revoked_at
        or min(record.idle_expires_at, record.absolute_expires_at) <= now
    ):
        fail(401, "SESSION_REQUIRED", "Please sign in to continue.")
    user = db.get(User, record.user_id)
    if not user:
        fail(401, "SESSION_REQUIRED", "Please sign in to continue.")
    if record.idle_expires_at - now < timedelta(hours=settings.session_idle_hours, minutes=-5):
        record.idle_expires_at = min(
            now + timedelta(hours=settings.session_idle_hours), record.absolute_expires_at
        )
        if commit_idle:
            db.commit()
    return user, record


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def rate_limit(request: Request, identity: str) -> None:
    peer = request.client.host if request.client else "unknown"
    try:
        for key, cap in [("ip:" + token_hash(peer), 40), ("identity:" + token_hash(identity), 10)]:
            allowed = request.app.state.redis.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],900) end; return n",
                1,
                "auth:" + key,
            )
            if int(allowed) > cap:
                fail(429, "RATE_LIMITED", "Too many attempts. Try again in 15 minutes.")
    except (RedisError, ConnectionError, OSError):
        fail(503, "AUTH_UNAVAILABLE", "Sign-in is temporarily unavailable.")
