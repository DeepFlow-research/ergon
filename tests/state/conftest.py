"""Shared fixtures for state tests.

Module-scoped in-memory SQLite engine with per-test transaction rollback
so every test sees a clean database without the cost of re-creating tables.
"""

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

import ergon_core.core.persistence.context.models as _context_models  # noqa: F401
import ergon_core.core.persistence.definitions.models as _def_models  # noqa: F401
import ergon_core.core.persistence.graph.models as _graph_models  # noqa: F401
import ergon_core.core.persistence.telemetry.models as _telemetry_models  # noqa: F401


@pytest.fixture(scope="module")
def engine() -> Engine:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(e)
    return e


@pytest.fixture
def session(engine: Engine):
    conn = engine.connect()
    txn = conn.begin()
    sess = Session(bind=conn)
    yield sess
    sess.close()
    txn.rollback()
    conn.close()
