from collections.abc import Generator

from fastapi import Request
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def make_sessions(url: str) -> sessionmaker[Session]:
    return sessionmaker(create_engine(url, pool_pre_ping=True), expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.sessions() as session:
        yield session
