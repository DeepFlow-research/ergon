"""Run and task status enums.

StrEnum: DB columns store string literals. StrEnum gives both Python
type safety and Postgres VARCHAR/JSON compatibility.
"""

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class TaskExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TrainingStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunResourceKind(StrEnum):
    """Canonical kinds for ``run_resources.kind``.

    Stored as VARCHAR; enforced at the model/API boundary, not in the DB
    schema. Each kind documents the publisher that produces it so a new
    reader can trace a row back to the code that wrote it.
    """

    OUTPUT = "output"
    """Explicit text artifact published by a worker/toolkit.

    Worker final assistant messages belong on
    ``RunTaskExecution.final_assistant_message`` instead of this resource log.
    """

    REPORT = "report"
    """Terminal report written by a worker into a sandbox publish directory."""

    ARTIFACT = "artifact"
    """Intermediate file a worker saved into a publish directory."""

    SEARCH_CACHE = "search_cache"
    """Raw JSON search payload cached by a search toolkit."""

    NOTE = "note"
    """Free-form scratch note written by an agent."""

    IMPORT = "import"
    """Copied snapshot materialized from another ``RunResource``."""
