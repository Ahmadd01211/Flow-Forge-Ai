import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.identity import account
from app.modules.identity.models import User
from app.modules.identity.service import (
    check_csrf,
    cookie,
    create_session,
    csrf_token,
    current_session,
    dummy_hash,
    hasher,
    rate_limit,
    verify_password,
)
from app.modules.workspaces.models import Workspace, WorkspaceMember

router = APIRouter(prefix="/auth", tags=["identity"])


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Register(Login):
    name: str = Field(min_length=1, max_length=100)
    workspace_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)


def session_payload(db: Session, user: User, raw: str, request: Request) -> dict:
    members = db.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
    ).all()
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "email_verified": user.email_verified_at is not None,
        },
        "csrf_token": csrf_token(raw, request.app.state.settings),
        "workspaces": [{"id": w.id, "name": w.name, "role": m.role} for w, m in members],
    }


@router.get("/csrf")
def csrf(request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie) or request.cookies.get(
        settings.preauth_cookie
    )
    if not raw:
        raw = secrets.token_urlsafe(32)
        cookie(response, settings, settings.preauth_cookie, raw, 3600)
    return {"csrf_token": csrf_token(raw, settings)}


@router.post("/register", status_code=201, dependencies=[Depends(check_csrf)])
def register(
    body: Register, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    email = str(body.email).lower()
    rate_limit(request, email)
    user = User(email=email, name=body.name.strip(), password_hash=hasher.hash(body.password))
    if not user.name or not body.workspace_name.strip():
        fail(422, "NAME_REQUIRED", "Please enter a name and workspace name.")
    try:
        db.add(user)
        db.flush()
        workspace = Workspace(name=body.workspace_name.strip(), created_by=user.id)
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        raw = create_session(db, user, response, request.app.state.settings)
        account.issue(db, user, "verify", request.app.state.settings)
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "REGISTRATION_UNAVAILABLE", "Unable to create this account. Try signing in.")
    return session_payload(db, user, raw, request)


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    email = str(body.email).lower()
    rate_limit(request, email)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    verified = verify_password(user.password_hash if user else dummy_hash, body.password)
    if not user or not verified:
        fail(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(body.password)
    # Rotate any existing session instead of leaving a stale active login behind.
    if request.cookies.get(request.app.state.settings.session_cookie):
        try:
            _, existing = current_session(request, db, commit_idle=False)
            existing.revoked_at = datetime.now(UTC)
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
    raw = create_session(db, user, response, request.app.state.settings)
    db.commit()
    return session_payload(db, user, raw, request)


@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)) -> dict:
    user, _ = current_session(request, db)
    return session_payload(
        db, user, request.cookies[request.app.state.settings.session_cookie], request
    )


@router.post("/logout", status_code=204, dependencies=[Depends(check_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    _, record = current_session(request, db)
    record.revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(
        request.app.state.settings.session_cookie,
        path="/",
        secure=request.app.state.settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128)


class PasswordReset(TokenRequest):
    password: str = Field(min_length=12, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)


@router.post("/forgot-password", dependencies=[Depends(check_csrf)])
def forgot(body: EmailRequest, request: Request, db: Session = Depends(get_db)):
    email = str(body.email).lower()
    rate_limit(request, "reset:" + email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        account.issue(db, user, "reset", request.app.state.settings)
        db.commit()
    return {"message": "If this account exists, a reset link will arrive by email."}


@router.post("/reset-password", dependencies=[Depends(check_csrf)])
def reset(body: PasswordReset, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "token:" + body.token)
    user = account.consume(db, body.token, "reset")
    user.password_hash = hasher.hash(body.password)
    account.revoke_sessions(db, user.id)
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}


@router.post("/verification-email", dependencies=[Depends(check_csrf)])
def verification_email(request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    rate_limit(request, "verify:" + str(user.id))
    if not user.email_verified_at:
        account.issue(db, user, "verify", request.app.state.settings)
        db.commit()
    return {"message": "Check your email for a verification link."}


@router.post("/verify-email", dependencies=[Depends(check_csrf)])
def verify_email(body: TokenRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "token:" + body.token)
    user = account.consume(db, body.token, "verify")
    user.email_verified_at = datetime.now(UTC)
    db.commit()
    return {"message": "Email verified. You can now accept workspace invitations."}


@router.post("/change-password", dependencies=[Depends(check_csrf)])
def change_password(body: PasswordChange, request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    rate_limit(request, "password:" + str(user.id))
    user = db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not verify_password(user.password_hash, body.current_password):
        fail(401, "INVALID_CREDENTIALS", "Current password is incorrect.")
    user.password_hash = hasher.hash(body.password)
    account.revoke_sessions(db, user.id)
    db.commit()
    return {"message": "Password updated. Sign in again on your devices."}


@router.post("/logout-all", dependencies=[Depends(check_csrf)])
def logout_all(request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    account.revoke_sessions(db, user.id)
    db.commit()
    return {"message": "All sessions have been signed out."}
