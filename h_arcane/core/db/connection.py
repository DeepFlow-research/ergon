"""Database connection and session management."""

from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

from h_arcane.settings import settings

# Create engine with connection pooling
_engine = None


def get_engine():
    """Get SQLModel engine with connection pooling."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session() -> Generator[Session, None, None]:
    """Get database session (context manager)."""
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Initialize database - create all tables."""
    # Import all models so they register with SQLModel.metadata
    # This must happen BEFORE create_all() is called
    from h_arcane.core.db import models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    print("✅ Database tables created successfully")
