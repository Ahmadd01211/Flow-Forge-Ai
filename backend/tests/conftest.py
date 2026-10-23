import os
import secrets

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings


@pytest.fixture(scope="session")
def migrated_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration requires TEST_DATABASE_URL")
    if not make_url(url).database.endswith("_test"):
        raise RuntimeError("Tests refuse to reset a database without the _test suffix")
    from app.core.db import Base

    engine = create_engine(url)
    from app.main import create_app  # noqa: F401 -- register all module metadata

    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def client(migrated_database, tmp_path):
    from app.core.db import Base
    from app.main import create_app

    engine = migrated_database
    key_path = tmp_path / "credential.key"
    key_path.write_bytes(secrets.token_bytes(32))
    with engine.begin() as connection:
        tables = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    settings = Settings(
        database_url=engine.url.render_as_string(hide_password=False),
        session_signing_key="test-key-" * 8,
        redis_url=os.environ.get("TEST_REDIS_URL", "redis://redis:6379/15"),
        public_origin="http://testserver",
        credential_key_path=str(key_path),
    )
    app = create_app(settings)
    app.state.redis.flushdb()
    with TestClient(app) as client:
        yield client
    app.state.sessions.kw["bind"].dispose()


def register(client, email="owner@example.com"):
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    result = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "a-unique-password-2026",
            "name": "Alex Morgan",
            "workspace_name": "Acme operations",
        },
        headers={"Origin": "http://testserver", "X-CSRF-Token": token},
    )
    assert result.status_code == 201, result.text
    return result.json()


def headers(client):
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
    }


@pytest.fixture()
def owner(client):
    return register(client)


@pytest.fixture()
def db(client):
    with client.app.state.sessions() as session:
        yield session
