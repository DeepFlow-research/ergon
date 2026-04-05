"""Database connection and session management."""

from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from h_arcane.core.settings import Settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # Instantiate Settings here (not the module singleton) so the URL reflects env
    # vars set after import (e.g. integration tests' __main__ blocks).
    url = Settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def create_all_tables() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Session:
    return Session(get_engine())
