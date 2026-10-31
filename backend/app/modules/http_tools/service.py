import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit

from redis.exceptions import RedisError
from sqlalchemy import func, select

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.db import make_sessions
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors, validate_user_schema
from app.modules.audit.service import record
from app.modules.http_tools.models import HttpTool
from app.modules.http_tools.transport import request
from app.modules.workspaces.models import Workspace

HEADER = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]{0,63}$")
FORBIDDEN_HEADERS = {
    "host",
    "cookie",
    "set-cookie",
    "connection",
    "content-length",
    "content-type",
    "transfer-encoding",
    "upgrade",
    "origin",
    "referer",
    "accept",
    "accept-encoding",
    "proxy-authorization",
    "forwarded",
    "te",
    "trailer",
    "user-agent",
    "x-real-ip",
    "x-original-url",
    "x-rewrite-url",
    "x-http-method",
    "x-http-method-override",
    "x-method-override",
}


def no_embedded_credential(value, secret):
    if not secret:
        return
    if isinstance(value, str) and secret in value:
        fail(
            422,
            "HTTP_AUTH_INVALID",
            "Put the credential only in its credential field, rather than tool metadata, schemas or URLs.",
        )
    if isinstance(value, dict):
        for key, item in value.items():
            no_embedded_credential(key, secret)
            no_embedded_credential(item, secret)
    elif isinstance(value, list):
        for item in value:
            no_embedded_credential(item, secret)


def digest(spec):
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def public(row):
    return {
        "id": row.id,
        **row.spec,
        "state": row.state,
        "generation": row.generation,
        "spec_hash": row.spec_hash,
        "credential_present": bool(row.ciphertext),
        "created_at": row.created_at,
    }


def credential(value, mode):
    secret = value.get_secret_value() if value is not None else ""
    if mode == "none":
        if secret:
            fail(
                422,
                "HTTP_AUTH_INVALID",
                "Choose an authentication mode before supplying a credential.",
            )
        return ""
    if not 8 <= len(secret) <= 4096 or any(ord(char) < 32 or ord(char) > 126 for char in secret):
        fail(
            422,
            "HTTP_AUTH_INVALID",
            "Use an 8–4096 character header credential without control characters.",
        )
    return secret


def find(db, workspace_id, tool_id, lock=False):
    query = select(HttpTool).where(HttpTool.workspace_id == workspace_id, HttpTool.id == tool_id).execution_options(populate_existing=True)
    row = db.scalar(
        query.with_for_update().execution_options(populate_existing=True) if lock else query
    )
    if not row:
        fail(404, "HTTP_TOOL_NOT_FOUND", "HTTP tool not found.")
    return row


def check_test_rate(redis, workspace_id):
    try:
        pipe = redis.pipeline()
        pipe.incr(f"http-test:{workspace_id}")
        pipe.expire(f"http-test:{workspace_id}", 60, nx=True)
        count, _ = pipe.execute()
    except RedisError:
        fail(503, "RATE_LIMIT_UNAVAILABLE", "Remote tool testing is temporarily unavailable.")
    if count > 20:
        fail(429, "HTTP_TEST_RATE_LIMIT", "This workspace reached its HTTP test limit. Try again shortly.")


def create(db, workspace_id, actor_id, body, settings):
    from app.modules.http_tools.transport import canonical_url, public_address

    if not body.confirm_permissions:
        fail(
            422,
            "HTTP_APPROVAL_REQUIRED",
            "Approve this destination and method for the workspace first.",
        )
    if not body.name.strip() or body.read_only and body.method != "GET":
        fail(
            422,
            "HTTP_PERMISSION_INVALID",
            "Only an explicitly reviewed GET endpoint can be granted to agents.",
        )
    validate_user_schema(body.input_schema)
    validate_user_schema(body.output_schema)
    header = (
        "Authorization"
        if body.auth_mode == "bearer"
        else body.auth_header
        if body.auth_mode == "api_key"
        else ""
    )
    if body.auth_mode == "api_key" and (
        not HEADER.fullmatch(header)
        or header.lower() in FORBIDDEN_HEADERS
        or header.lower().startswith(("x-forwarded-", "proxy-"))
    ):
        fail(
            422,
            "HTTP_AUTH_INVALID",
            "Choose a dedicated API-key header rather than a routing, cookie or transport header.",
        )
    secret = credential(body.credential, body.auth_mode)
    spec = body.model_dump(exclude={"credential", "confirm_permissions"})
    spec.update(name=body.name.strip(), url=canonical_url(body.url), auth_header=header)
    no_embedded_credential([spec, body.url], secret)
    bounded_json(spec, max_bytes=150000)
    public_address(urlsplit(spec["url"]).hostname)
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    count = db.scalar(
        select(func.count())
        .select_from(HttpTool)
        .where(HttpTool.workspace_id == workspace_id, HttpTool.state == "active")
    )
    if count >= 50:
        fail(
            422,
            "HTTP_TOOL_LIMIT",
            "Revoke an unused HTTP tool before adding another; the workspace limit is 50.",
        )
    row = HttpTool(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by=actor_id,
        spec=spec,
        spec_hash=digest(spec),
        generation=1,
        state="active",
    )
    if secret:
        row.nonce, row.ciphertext = encrypt_secret(
            load_master_key(settings.credential_key_path), workspace_id, row.id, 1, secret
        )
    db.add(row)
    record(
        db,
        workspace_id,
        actor_id,
        "http_tool.approved",
        row.id,
        {"method": body.method, "read_only": body.read_only},
    )
    db.commit()
    return public(row)


def resolve(db, workspace_id, grant, pinned=True, agent=False):
    try:
        identity = uuid.UUID(str(grant["tool_id"]))
    except (KeyError, TypeError, ValueError):
        fail(422, "HTTP_TOOL_INVALID", "Select an approved HTTP tool.")
    row = find(db, workspace_id, identity)
    if row.state != "active" or row.spec_hash != digest(row.spec):
        fail(
            409,
            "HTTP_TOOL_CHANGED",
            "This HTTP tool was revoked or its specification changed. Republish after reviewing it.",
        )
    if agent and (row.spec["method"] != "GET" or not row.spec["read_only"]):
        fail(
            422,
            "HTTP_WRITE_GRANT_DENIED",
            "Agents can use reviewed read-only GET tools. Use a published workflow for write actions.",
        )
    if pinned and (
        row.generation != grant.get("connection_generation")
        or row.spec_hash != grant.get("spec_hash")
    ):
        fail(
            409,
            "HTTP_TOOL_CHANGED",
            "The HTTP credential or specification changed. Publish a new version.",
        )
    if (
        "input_schema" in grant
        and pinned
        and digest(grant["input_schema"]) != digest(row.spec["input_schema"])
    ):
        fail(409, "HTTP_TOOL_CHANGED", "The published HTTP input contract changed.")
    return row


def pin(db, workspace_id, grants, agent=True):
    result = []
    for grant in grants:
        row = resolve(db, workspace_id, grant, pinned=False, agent=agent)
        result.append(
            {
                "tool_id": str(row.id),
                "connection_generation": row.generation,
                "spec_hash": row.spec_hash,
                "name": row.spec["name"],
                "description": row.spec["description"],
                "input_schema": row.spec["input_schema"],
            }
        )
    bounded_json(result, max_bytes=65536)
    return result


def validate_grants(db, workspace_id, config):
    for grant in config.get("http_tools", []):
        resolve(db, workspace_id, grant, agent=True)


def alias(grant):
    return "http_" + uuid.UUID(grant["tool_id"]).hex[:24]


def invoke(db, workspace_id, grant, arguments, settings, timeout=12, agent=False):
    row = resolve(db, workspace_id, grant, agent=agent)
    if not isinstance(arguments, dict):
        fail(422, "HTTP_INPUT_SCHEMA_INVALID", "HTTP tool input must be an object.")
    bounded_json(arguments, max_bytes=65536)
    if example_errors(row.spec["input_schema"], arguments, "input"):
        fail(
            422,
            "HTTP_INPUT_SCHEMA_INVALID",
            "Input does not match the approved HTTP tool contract.",
        )
    secret = (
        decrypt_secret(
            load_master_key(settings.credential_key_path),
            workspace_id,
            row.id,
            row.generation,
            row.nonce,
            row.ciphertext,
        )
        if row.ciphertext and row.nonce
        else ""
    )
    output = request(row.spec, secret, arguments, timeout)
    if example_errors(row.spec["output_schema"], output, "output"):
        fail(
            502,
            "HTTP_OUTPUT_SCHEMA_INVALID",
            "The API response does not match the approved output contract.",
        )
    return output


def invoke_agent(settings, workspace_id, grant, arguments, timeout):
    sessions = make_sessions(settings.database_url)
    try:
        with sessions() as db:
            return invoke(
                db, workspace_id, grant, arguments, settings, timeout=min(12.0, timeout), agent=True
            )
    finally:
        sessions.kw["bind"].dispose()
