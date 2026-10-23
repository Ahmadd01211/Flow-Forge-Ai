from sqlalchemy import text


def test_readiness_requires_current_migration(client, db):
    assert client.get("/health/ready").status_code == 200
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    try:
        db.execute(text("UPDATE alembic_version SET version_num='outdated'"))
        db.commit()
        assert client.get("/health/ready").status_code == 503
    finally:
        db.execute(text("UPDATE alembic_version SET version_num=:revision"), {"revision": current})
        db.commit()
    assert client.get("/health/ready").status_code == 200
