import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.agents.models import Agent
from app.modules.audit.service import record
from app.modules.identity.mail import enqueue
from app.modules.identity.models import User
from app.modules.identity.service import check_csrf, current_session, rate_limit, token_hash
from app.modules.workflows.models import Workflow
from app.modules.workspaces.models import Workspace, WorkspaceInvitation, WorkspaceMember
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def administration(workspace_id, request, db):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "Workspace administration is required.")
    # Serialize membership changes and re-check access after acquiring the lock.
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    member = db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.id == member.id)
        .execution_options(populate_existing=True)
    )
    if not member or member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "Workspace administration is required.")
    return workspace, member


class WorkspaceName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: Literal["admin", "editor", "viewer"] = "editor"


class RoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["owner", "admin", "editor", "viewer"]


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128)


@router.post("", status_code=201, dependencies=[Depends(check_csrf)])
def create_workspace(body: WorkspaceName, request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    rate_limit(request, "workspace:" + str(user.id))
    if not body.name.strip():
        fail(422, "NAME_REQUIRED", "Enter a workspace name.")
    row = Workspace(name=body.name.strip(), created_by=user.id)
    db.add(row)
    db.flush()
    db.add(WorkspaceMember(workspace_id=row.id, user_id=user.id, role="owner"))
    db.commit()
    return {"id": row.id, "name": row.name, "role": "owner"}


@router.post("/accept-invitation", dependencies=[Depends(check_csrf)])
def accept_invitation(body: InvitationAccept, request: Request, db: Session = Depends(get_db)):
    user, _ = current_session(request, db)
    rate_limit(request, "invite:" + str(user.id))
    candidate = db.scalar(
        select(WorkspaceInvitation).where(WorkspaceInvitation.token_hash == token_hash(body.token))
    )
    if not candidate:
        fail(400, "INVITATION_INVALID", "This invitation expired or was already used.")
    db.scalar(select(Workspace).where(Workspace.id == candidate.workspace_id).with_for_update())
    invite = db.scalar(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invite.consumed_at or invite.expires_at <= datetime.now(UTC):
        fail(400, "INVITATION_INVALID", "This invitation expired or was already used.")
    if user.email != invite.email or not user.email_verified_at:
        fail(
            403,
            "INVITATION_IDENTITY",
            "Sign in and verify the email address that received this invitation.",
        )
    inviter = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == invite.workspace_id,
            WorkspaceMember.user_id == invite.created_by,
        )
    )
    if (
        not inviter
        or inviter.role not in {"owner", "admin"}
        or (invite.role == "admin" and inviter.role != "owner")
    ):
        fail(
            403,
            "INVITATION_REVOKED",
            "The inviter no longer has permission to grant this access. Request a new invitation.",
        )
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == invite.workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    if not member:
        db.add(WorkspaceMember(workspace_id=invite.workspace_id, user_id=user.id, role=invite.role))
    # Accepting an invite must never downgrade or elevate an existing membership.
    invite.consumed_at = datetime.now(UTC)
    record(db, invite.workspace_id, user.id, "workspace.invitation_accepted", invite.id, {})
    db.commit()
    return {"workspace_id": invite.workspace_id}


@router.patch("/{workspace_id}", dependencies=[Depends(check_csrf)])
def rename_workspace(
    workspace_id: uuid.UUID, body: WorkspaceName, request: Request, db: Session = Depends(get_db)
):
    workspace, member = administration(workspace_id, request, db)
    if not body.name.strip():
        fail(422, "NAME_REQUIRED", "Enter a workspace name.")
    workspace.name = body.name.strip()
    record(db, workspace_id, member.user_id, "workspace.renamed", workspace_id, {})
    db.commit()
    return {"id": workspace.id, "name": workspace.name, "role": member.role}


@router.get("/{workspace_id}/members")
def members(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    administration(workspace_id, request, db)
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.name)
        .limit(100)
    ).all()
    return {
        "items": [
            {"id": m.id, "user_id": u.id, "name": u.name, "email": u.email, "role": m.role}
            for m, u in rows
        ]
    }


@router.patch("/{workspace_id}/members/{member_id}", dependencies=[Depends(check_csrf)])
def change_role(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    body: RoleRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _, actor = administration(workspace_id, request, db)
    target = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id
        )
    )
    if not target:
        fail(404, "NOT_FOUND", "Member not found.")
    if actor.role != "owner" and (
        target.role in {"owner", "admin"} or body.role in {"owner", "admin"}
    ):
        fail(403, "FORBIDDEN", "Only an owner can manage administrators or owners.")
    if target.role == "owner" and body.role != "owner":
        owners = db.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner")
        )
        if owners <= 1:
            fail(409, "LAST_OWNER", "Promote another owner before changing the last owner.")
    target.role = body.role
    record(
        db,
        workspace_id,
        actor.user_id,
        "workspace.member_role_changed",
        target.id,
        {"role": body.role},
    )
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete("/{workspace_id}/members/{member_id}", dependencies=[Depends(check_csrf)])
def remove_member(
    workspace_id: uuid.UUID, member_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    _, actor = administration(workspace_id, request, db)
    target = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id, WorkspaceMember.workspace_id == workspace_id
        )
    )
    if not target:
        fail(404, "NOT_FOUND", "Member not found.")
    if target.role == "owner":
        fail(409, "OWNER_PROTECTED", "Change this owner's role before removing them.")
    if actor.role != "owner" and target.role == "admin":
        fail(403, "FORBIDDEN", "Only an owner can remove an administrator.")
    record(db, workspace_id, actor.user_id, "workspace.member_removed", target.id, {})
    db.delete(target)
    db.commit()
    return {"message": "Member removed."}


@router.get("/{workspace_id}/invitations")
def invitations(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    administration(workspace_id, request, db)
    rows = db.scalars(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.consumed_at.is_(None),
            WorkspaceInvitation.expires_at > datetime.now(UTC),
        )
        .limit(100)
    ).all()
    return {
        "items": [
            {"id": r.id, "email": r.email, "role": r.role, "expires_at": r.expires_at} for r in rows
        ]
    }


@router.post("/{workspace_id}/invitations", status_code=201, dependencies=[Depends(check_csrf)])
def invite(
    workspace_id: uuid.UUID, body: InviteRequest, request: Request, db: Session = Depends(get_db)
):
    workspace, member = administration(workspace_id, request, db)
    rate_limit(request, "invitations:" + str(member.user_id))
    user = db.get(User, member.user_id)
    if not user.email_verified_at:
        fail(403, "EMAIL_UNVERIFIED", "Verify your email before inviting teammates.")
    if body.role == "admin" and member.role != "owner":
        fail(403, "FORBIDDEN", "Only owners can invite administrators.")
    email = str(body.email).lower()
    existing = db.scalar(
        select(WorkspaceMember)
        .join(User, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id, User.email == email)
    )
    if existing:
        fail(409, "ALREADY_MEMBER", "This person is already a member.")
    now = datetime.now(UTC)
    for old in db.scalars(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == email,
            WorkspaceInvitation.consumed_at.is_(None),
        )
    ):
        if old.role == "admin" and member.role != "owner":
            fail(403, "FORBIDDEN", "Only an owner can replace an administrator invitation.")
        old.consumed_at = now
    raw = secrets.token_urlsafe(32)
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        email=email,
        role=body.role,
        token_hash=token_hash(raw),
        created_by=member.user_id,
        expires_at=now + timedelta(days=7),
    )
    db.add(invitation)
    db.flush()
    enqueue(
        db,
        request.app.state.settings,
        member.user_id,
        email,
        "Your FlowForge workspace invitation",
        f"You have been invited to {workspace.name} as {body.role}.\nSign in or register with this email, verify it, then open:\n{request.app.state.settings.public_origin}/accept-invitation#{raw}",
    )
    record(
        db, workspace_id, member.user_id, "workspace.invited", invitation.id, {"role": body.role}
    )
    db.commit()
    return {
        "id": invitation.id,
        "email": email,
        "role": body.role,
        "expires_at": invitation.expires_at,
    }


@router.delete("/{workspace_id}/invitations/{invitation_id}", dependencies=[Depends(check_csrf)])
def revoke_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = administration(workspace_id, request, db)
    row = db.scalar(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.id == invitation_id,
        )
    )
    if not row:
        fail(404, "NOT_FOUND", "Invitation not found.")
    if row.role == "admin" and member.role != "owner":
        fail(403, "FORBIDDEN", "Only an owner can manage administrator invitations.")
    row.consumed_at = datetime.now(UTC)
    record(db, workspace_id, member.user_id, "workspace.invitation_revoked", row.id, {})
    db.commit()
    return {"message": "Invitation revoked."}


@router.get("/{workspace_id}")
def workspace(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    row, member = authorize(request, db, workspace_id)
    return {"id": row.id, "name": row.name, "role": member.role}


@router.get("/{workspace_id}/overview")
def overview(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id)
    return {
        "agents": db.scalar(
            select(func.count())
            .select_from(Agent)
            .where(Agent.workspace_id == workspace_id, Agent.archived_at.is_(None))
        ),
        "workflows": db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.workspace_id == workspace_id)
        ),
        "execution_enabled": False,
    }
