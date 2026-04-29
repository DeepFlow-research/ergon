"""normalize_evaluation_summary_nulls

Revision ID: e5f6a7b8c9d0
Revises: d4f5a6b7c8d9
Create Date: 2026-04-25 20:57:00.000000

Normalize persisted evaluation summary JSON so optional criterion text fields
use JSON null instead of empty-string sentinels, and every criterion result has
explicit required rubric fields before the typed parser requires them.
"""

from copy import deepcopy
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_description(entry: dict) -> None:
    criterion_description = entry.get("criterion_description")
    if isinstance(criterion_description, str) and criterion_description != "":
        return

    criterion_name = entry.get("criterion_name")
    entry["criterion_description"] = (
        criterion_name
        if isinstance(criterion_name, str) and criterion_name
        else "unknown criterion"
    )


def _normalize_nullable_text(entry: dict, field_name: str) -> None:
    if entry.get(field_name) == "":
        entry[field_name] = None
    else:
        entry.setdefault(field_name, None)


def _normalize_error(entry: dict) -> None:
    error = entry.get("error")
    if error == "":
        entry["error"] = None
    elif isinstance(error, str):
        entry["error"] = {"kind": error}
    else:
        entry.setdefault("error", None)


def _normalize_status(entry: dict) -> None:
    if entry.get("status") in {"passed", "failed", "errored", "skipped"}:
        return

    if entry.get("error") is not None:
        entry["status"] = "errored"
    elif entry.get("skipped_reason") is not None:
        entry["status"] = "skipped"
    else:
        entry["status"] = "passed" if entry.get("passed") is True else "failed"


def _normalize_scoring(entry: dict) -> None:
    entry.setdefault("weight", 1.0)
    if "contribution" in entry:
        return

    score = entry.get("score")
    entry["contribution"] = score if isinstance(score, int | float) else 0.0


def _normalize_criterion_result(entry: dict) -> None:
    _normalize_description(entry)
    _normalize_nullable_text(entry, "feedback")
    _normalize_nullable_text(entry, "evaluation_input")
    _normalize_error(entry)
    _normalize_nullable_text(entry, "skipped_reason")
    entry.setdefault("model_reasoning", None)
    _normalize_status(entry)
    _normalize_scoring(entry)


def _normalize_summary_json(summary_json: dict) -> dict:
    normalized = deepcopy(summary_json)
    criterion_results = normalized.get("criterion_results")
    if not isinstance(criterion_results, list):
        return normalized

    for entry in criterion_results:
        if isinstance(entry, dict):
            _normalize_criterion_result(entry)

    return normalized


def _denormalize_summary_json(summary_json: dict) -> dict:
    denormalized = deepcopy(summary_json)
    criterion_results = denormalized.get("criterion_results")
    if not isinstance(criterion_results, list):
        return denormalized

    for entry in criterion_results:
        if not isinstance(entry, dict):
            continue
        if entry.get("feedback") is None:
            entry["feedback"] = ""
        if entry.get("evaluation_input") is None:
            entry["evaluation_input"] = ""
        entry.pop("status", None)
        entry.pop("contribution", None)
        entry.pop("model_reasoning", None)
        entry.pop("skipped_reason", None)

    return denormalized


def _rewrite_summaries(*, normalize: bool) -> None:
    evaluations = sa.table(
        "run_task_evaluations",
        sa.column("id", sa.Uuid()),
        sa.column("summary_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(evaluations.c.id, evaluations.c.summary_json))

    for row in rows:
        summary_json = row.summary_json
        if not isinstance(summary_json, dict):
            continue

        rewritten = (
            _normalize_summary_json(summary_json)
            if normalize
            else _denormalize_summary_json(summary_json)
        )
        if rewritten == summary_json:
            continue

        connection.execute(
            evaluations.update().where(evaluations.c.id == row.id).values(summary_json=rewritten)
        )


def upgrade() -> None:
    _rewrite_summaries(normalize=True)


def downgrade() -> None:
    _rewrite_summaries(normalize=False)
