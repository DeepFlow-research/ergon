"""Guard against enum drift between Python and the Postgres ``taskexecutionstatus`` type.

Background
----------
The initial schema (``5f01559f2bc3_initial_schema_v2``) created the Postgres
``taskexecutionstatus`` enum with only ``PENDING, RUNNING, COMPLETED, FAILED,
SKIPPED``. ``CANCELLED`` was added to the Python ``TaskExecutionStatus`` enum
later (alongside the graph-side containment change in
``b5b36e45e5e6_add_containment_and_cancelled``), but the Postgres enum was
never extended — causing every ``ergon-core-cleanup-cancelled-task`` Inngest
invocation to fail with
``invalid input value for enum taskexecutionstatus: "CANCELLED"``
(see ``docs/bugs/open/2026-04-23-inngest-function-failures.md`` § B).

The migration that fixes it lives at
``ergon_core/migrations/versions/84519b3f8431_add_cancelled_to_taskexecutionstatus_enum.py``.

This test is a cheap regression guard that runs without a database: it
asserts the Python enum contains exactly the set of values that the
Postgres enum is expected to carry after that migration is applied.
Whenever a new value is added on either side, this test will fail and
force the author to also ship (or audit) the matching ``ALTER TYPE``
migration.

Follow-up
---------
A real-database equivalent — round-tripping each enum value through a
throwaway ``run_task_executions`` row against a real Postgres fixture —
is a follow-up. The repo's existing state/unit tests run on SQLite, and
SQLite renders ``sa.Enum`` as VARCHAR so it cannot catch this class of
drift.
"""

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus

# Keep this set in sync with the Postgres ``taskexecutionstatus`` enum,
# which after migration ``4a71a3dc2ef5`` contains:
#     PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, CANCELLED, BLOCKED
EXPECTED_MEMBERS = {
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
    "CANCELLED",
    "BLOCKED",
}


def test_task_execution_status_has_expected_members() -> None:
    actual = {m.name for m in TaskExecutionStatus}
    assert actual == EXPECTED_MEMBERS, (
        "TaskExecutionStatus drifted from the Postgres enum. "
        "If you added a value, also add an ALTER TYPE migration "
        "(see 84519b3f8431_add_cancelled_to_taskexecutionstatus_enum.py). "
        f"Expected {EXPECTED_MEMBERS}, got {actual}."
    )


def test_cancelled_member_present() -> None:
    # Explicit regression assertion for the 2026-04-23 bug.
    assert TaskExecutionStatus.CANCELLED.value == "cancelled"
