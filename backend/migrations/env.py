from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401 -- same registration as independent workers
from app.core.config import Settings
from app.core.db import Base

target_metadata = Base.metadata
url = Settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    context.configure(
        connection=context.config.attributes["connection"], target_metadata=target_metadata
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
