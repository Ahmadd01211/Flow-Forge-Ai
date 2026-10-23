import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.identity.service import check_csrf, rate_limit
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    ConnectionList,
    ConnectionRead,
    DefaultModelUpdate,
    ProviderCredential,
)
from app.modules.workspaces.service import authorize
from app.providers.registry import Provider

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"])


@router.get("", response_model=ConnectionList)
def connections(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authorize(request, db, workspace_id)
    return service.list_connections(db, workspace_id)


@router.post("/provider", response_model=ConnectionRead, dependencies=[Depends(check_csrf)])
def connect(
    workspace_id: uuid.UUID,
    body: ProviderCredential,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    rate_limit(request, "provider:" + str(workspace_id))
    return service.upsert_connection(request, db, workspace_id, member.user_id, body)


@router.post(
    "/providers/{provider}", response_model=ConnectionRead, dependencies=[Depends(check_csrf)]
)
def connect_named(
    workspace_id: uuid.UUID,
    provider: Provider,
    body: ProviderCredential,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    rate_limit(request, "provider:" + str(workspace_id))
    return service.upsert_connection(request, db, workspace_id, member.user_id, body, provider)


@router.post(
    "/providers/{provider}/refresh-models",
    response_model=ConnectionRead,
    dependencies=[Depends(check_csrf)],
)
def refresh_models(
    workspace_id: uuid.UUID, provider: Provider, request: Request, db: Session = Depends(get_db)
):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    rate_limit(request, "provider:" + str(workspace_id))
    return service.refresh_models(request, db, workspace_id, member.user_id, provider)


@router.patch(
    "/providers/{provider}/default-model",
    response_model=ConnectionRead,
    dependencies=[Depends(check_csrf)],
)
def choose_default_model(
    workspace_id: uuid.UUID,
    provider: Provider,
    body: DefaultModelUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    return service.set_default_model(db, workspace_id, member.user_id, provider, body)


@router.delete("/provider", response_model=ConnectionRead, dependencies=[Depends(check_csrf)])
def revoke(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    return service.revoke_connection(db, workspace_id, member.user_id)


@router.delete(
    "/providers/{provider}", response_model=ConnectionRead, dependencies=[Depends(check_csrf)]
)
def revoke_named(
    workspace_id: uuid.UUID,
    provider: Provider,
    request: Request,
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id)
    service.require_admin(member)
    return service.revoke_connection(db, workspace_id, member.user_id, provider)
