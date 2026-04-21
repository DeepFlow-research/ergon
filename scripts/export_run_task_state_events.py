"""One-shot export of run_task_state_events rows to JSONL.gz.

Run BEFORE applying the Alembic migration that drops the table.

Usage:
    uv run python scripts/export_run_task_state_events.py

Output: exports/run_task_state_events_<ISO8601_timestamp>.jsonl.gz

The archive is insurance. Most systems have 0 rows since propagation.py
stopped writing to this table. The script is idempotent — running it twice
produces two archive files; the table is not modified.
"""

from __future__ import annotations

import gzip
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure ergon_core is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ergon_core.core.persistence.shared.db import get_session
from sqlmodel import text


def main() -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    exports_dir = Path(__file__).parent.parent / "exports"
    exports_dir.mkdir(exist_ok=True)
    out_path = exports_dir / f"run_task_state_events_{timestamp}.jsonl.gz"

    row_count = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        with get_session() as session:
            rows = session.exec(
                text("SELECT * FROM run_task_state_events ORDER BY created_at")
            ).all()
            for row in rows:
                fh.write(json.dumps(dict(row._mapping)) + "\n")
                row_count += 1

    print(f"Exported {row_count} rows to {out_path}")


if __name__ == "__main__":
    main()
