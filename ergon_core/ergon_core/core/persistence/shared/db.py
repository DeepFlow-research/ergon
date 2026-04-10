"""Database connection and session management.

Schema is managed by Alembic — see ``ergon_core/migrations/``.
Call ``ensure_db()`` once per process to apply pending migrations.
"""

import logging
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from ergon_core.core.settings import Settings

logger = logging.getLogger(__name__)

_ERGON_CORE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ALEMBIC_INI = _ERGON_CORE_ROOT / "alembic.ini"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = Settings().database_url
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
