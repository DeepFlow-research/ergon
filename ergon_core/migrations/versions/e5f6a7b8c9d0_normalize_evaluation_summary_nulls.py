"""normalize_evaluation_summary_nulls

Revision ID: e5f6a7b8c9d0
Revises: d4f5a6b7c8d9
Create Date: 2026-04-25 20:57:00.000000

Normalize persisted evaluation summary JSON so optional criterion text fields
use JSON null instead of empty-string sentinels, and every criterion result has
an explicit description before the typed parser requires it.
"""

from copy import deepcopy
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_summary_json(summary_json: dict) -> dict:
    normalized = deepcopy(summary_json)
    criterion_results = normalized.get("criterion_results")
    if not isinstance(criterion_results, list):
        return normalized

    for entry in criterion_results:
        if not isinstance(entry, dict):
            continue

        criterion_description = entry.get("criterion_description")
        if not isinstance(criterion_description, str) or criterion_description == "":
            criterion_name = entry.get("criterion_name")
            entry["criterion_description"] = (
                criterion_name
                if isinstance(criterion_name, str) and criterion_name
                else "unknown criterion"
            )

        if entry.get("feedback") == "":
            entry["feedback"] = None
        else:
            entry.setdefault("feedback", None)

        if entry.get("evaluation_input") == "":
            entry["evaluation_input"] = None
        else:
            entry.setdefault("evaluation_input", None)

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
