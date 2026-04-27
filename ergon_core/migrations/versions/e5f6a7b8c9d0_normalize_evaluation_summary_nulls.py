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

        if entry.get("error") == "":
            entry["error"] = None
        elif isinstance(entry.get("error"), str):
            entry["error"] = {"kind": entry["error"]}
        else:
            entry.setdefault("error", None)

        skipped_reason = entry.get("skipped_reason")
        if skipped_reason == "":
            entry["skipped_reason"] = None
        else:
            entry.setdefault("skipped_reason", None)

        entry.setdefault("model_reasoning", None)

        passed = entry.get("passed")
        if entry.get("status") not in {"passed", "failed", "errored", "skipped"}:
            if entry.get("error") is not None:
                entry["status"] = "errored"
            elif entry.get("skipped_reason") is not None:
                entry["status"] = "skipped"
            else:
                entry["status"] = "passed" if passed is True else "failed"

        if "weight" not in entry:
            entry["weight"] = 1.0
        if "contribution" not in entry:
            score = entry.get("score")
            entry["contribution"] = score if isinstance(score, int | float) else 0.0

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
