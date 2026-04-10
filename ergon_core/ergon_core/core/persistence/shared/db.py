"""Database connection and session management.

Schema is managed by Alembic — see ``h_arcane/migrations/``.
Call ``ensure_db()`` once per process to apply pending migrations.
"""

import logging
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from h_arcane.core.settings import Settings

logger = logging.getLogger(__name__)

_H_ARCANE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ALEMBIC_INI = _H_ARCANE_ROOT / "alembic.ini"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = Settings().database_url
    return create_engine(url)


def ensure_db() -> None:
    """Run Alembic migrations to head (idempotent)."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_H_ARCANE_ROOT / "migrations"))
    command.upgrade(cfg, "head")
    logger.debug("Database migrated to head")


def get_session() -> Session:
    return Session(get_engine())
