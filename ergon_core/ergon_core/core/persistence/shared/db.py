"""Database connection and session management.

Schema is managed by Alembic — see ``ergon_core/migrations/``.
Call ``ensure_db()`` once per process to apply pending migrations.
"""

import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from ergon_core.core.shared.settings import Settings
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine

logger = logging.getLogger(__name__)

_ERGON_CORE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ALEMBIC_INI = _ERGON_CORE_ROOT / "alembic.ini"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = Settings().database_url
    if make_url(url).get_backend_name() == "postgresql":
        # Synchronous Sessions stay open across async notifications, so a
        # QueuePool at capacity would block the event loop their owners need.
        # PostgreSQL bounds connections instead; async Sessions would scale further.
        return create_engine(url, poolclass=NullPool)
    return create_engine(url)


def ensure_db() -> None:
    """Run Alembic migrations to head (idempotent).

    Safe to call from remote GPU nodes where the migrations directory may
    not exist — logs a warning and returns without migrating.
    """
    migrations_dir = _ERGON_CORE_ROOT / "migrations"
    if not migrations_dir.is_dir():
        logger.warning(
            "Alembic migrations directory not found at %s — "
            "skipping migration (assumes the database is already set up).",
            migrations_dir,
        )
        return
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(migrations_dir))
    command.upgrade(cfg, "head")
    logger.debug("Database migrated to head")


def get_session() -> Session:
    return Session(get_engine())


def lock_sample_transaction(session: Session, sample_id: UUID) -> None:
    """Serialize sample graph changes without locking unrelated sample telemetry."""
    if session.get_bind().dialect.name == "postgresql":
        # PostgreSQL releases this lock at commit/rollback. A UUID key collision
        # only serializes unrelated samples; it cannot weaken mutual exclusion.
        session.execute(
            text("SELECT pg_advisory_xact_lock(CAST(:sample_key AS BIGINT))"),
            {"sample_key": sample_id.int & ((1 << 63) - 1)},
        )
