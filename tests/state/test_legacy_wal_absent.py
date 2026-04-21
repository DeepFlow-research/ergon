"""Sentinel: run_task_state_events must not exist in the schema.

If someone re-introduces the table by copy-paste, this test fails immediately
in CI. The check runs against the same test DB used by all other state tests
(SQLite in tests, Postgres in integration).
"""

from sqlmodel import Session, text


def test_run_task_state_events_table_absent(session: Session) -> None:
    """The legacy table must not exist in the current schema."""
    # Works for both Postgres and SQLite.
    # Postgres: pg_tables is a system catalog view.
    # SQLite: sqlite_master is the schema table.
    try:
        # Postgres path
        result = session.exec(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename = 'run_task_state_events'"
            )
        ).all()
        assert result == [], (
            "run_task_state_events still exists in pg_tables — "
            "migration not applied or table re-created."
        )
    except Exception:
        # SQLite path (test environment)
        result = session.exec(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='run_task_state_events'"
            )
        ).all()
        assert result == [], (
            "run_task_state_events still exists in sqlite_master — "
            "SQLModel still has table=True for RunTaskStateEvent."
        )
