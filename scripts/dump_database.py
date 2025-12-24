"""Dump all database tables to a formatted log file for LLM consumption.

LLM UTILITY: This script exports all database tables to a human-readable log file
that can be easily consumed by LLMs (like Copilot) to understand experiment results
and debug issues.

Usage:
    python scripts/dump_database.py

    Or:
    python -m scripts.dump_database

Output:
    Creates a timestamped log file in the data directory:
    data/database_dump_YYYYMMDD_HHMMSS.log

The log file contains:
    - Summary statistics (row counts per table)
    - All data from all 9 tables formatted for readability:
      * experiments: GDPEval tasks with ground truth rubrics
      * runs: Experiment execution runs
      * messages: Worker-stakeholder conversation history
      * actions: Tool execution traces
      * resources: Input/output files
      * agent_configs: Agent configuration snapshots
      * evaluations: Aggregate evaluation results
      * criterion_results: Per-criterion evaluation scores
      * task_evaluation_results: Complete evaluation snapshots

Formatting:
    - UUIDs converted to strings
    - Datetimes in ISO format
    - JSON fields pretty-printed
    - Long strings truncated with length info
    - NULL values clearly marked

This is particularly useful for:
    - Sharing run results with LLM assistants for analysis
    - Debugging evaluation issues
    - Understanding experiment state without direct database access
    - Creating snapshots for analysis or reporting
"""

import json
from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from h_arcane.core.db.connection import get_session
from h_arcane.core.db.models import (
    Experiment,
    Run,
    Message,
    Action,
    Resource,
    AgentConfig,
    Evaluation,
    CriterionResult,
    TaskEvaluationResult,
)
from h_arcane.benchmarks.gdpeval.loader import DATA_DIR


def format_value(value):
    """Format a value for readable output."""
    if value is None:
        return "NULL"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        # Pretty print JSON with indentation
        return json.dumps(value, indent=2, default=str)
    if isinstance(value, str) and len(value) > 500:
        # Truncate very long strings but show more context
        return value[:500] + f"\n... (truncated, total length: {len(value)} chars)"
    return str(value)


def format_table_header(table_name: str, count: int) -> str:
    """Format a table header."""
    return f"\n{'=' * 80}\nTABLE: {table_name.upper()} ({count} rows)\n{'=' * 80}\n"


def format_row(row_dict: dict, row_num: int) -> str:
    """Format a single row."""
    lines = [f"\n--- Row {row_num} ---"]
    for key, value in row_dict.items():
        formatted_value = format_value(value)
        lines.append(f"  {key}: {formatted_value}")
    return "\n".join(lines)


def dump_table(session: Session, model_class, table_name: str) -> str:
    """Dump all rows from a table."""
    statement = select(model_class)
    rows = list(session.exec(statement).all())

    if not rows:
        return format_table_header(table_name, 0) + "\n(No rows)\n"

    output = [format_table_header(table_name, len(rows))]

    for i, row in enumerate(rows, 1):
        row_dict = row.model_dump(mode="json")
        output.append(format_row(row_dict, i))

    return "\n".join(output) + "\n"


def get_table_counts(session: Session) -> dict[str, int]:
    """Get row counts for all tables."""
    tables = [
        (Experiment, "experiments"),
        (Run, "runs"),
        (Message, "messages"),
        (Action, "actions"),
        (Resource, "resources"),
        (AgentConfig, "agent_configs"),
        (Evaluation, "evaluations"),
        (CriterionResult, "criterion_results"),
        (TaskEvaluationResult, "task_evaluation_results"),
    ]

    counts = {}
    for model_class, table_name in tables:
        try:
            statement = select(model_class)
            rows = list(session.exec(statement).all())
            counts[table_name] = len(rows)
        except Exception:
            counts[table_name] = -1  # Error indicator

    return counts


def dump_all_tables() -> str:
    """Dump all tables to a formatted string."""
    output = []
    output.append("=" * 80)
    output.append("DATABASE DUMP")
    output.append(f"Generated at: {datetime.utcnow().isoformat()} UTC")
    output.append("=" * 80)

    with next(get_session()) as session:
        # Get summary counts first
        counts = get_table_counts(session)
        output.append("\nSUMMARY:")
        output.append("-" * 80)
        for table_name, count in sorted(counts.items()):
            status = str(count) if count >= 0 else "ERROR"
            output.append(f"  {table_name:30} {status:>10} rows")
        output.append("-" * 80)

        # Define tables in logical order (parent tables first)
        tables = [
            (Experiment, "experiments"),
            (Run, "runs"),
            (Message, "messages"),
            (Action, "actions"),
            (Resource, "resources"),
            (AgentConfig, "agent_configs"),
            (Evaluation, "evaluations"),
            (CriterionResult, "criterion_results"),
            (TaskEvaluationResult, "task_evaluation_results"),
        ]

        for model_class, table_name in tables:
            try:
                table_output = dump_table(session, model_class, table_name)
                output.append(table_output)
            except Exception as e:
                output.append(f"\n{'=' * 80}\nERROR dumping {table_name}: {e}\n{'=' * 80}\n")

    return "\n".join(output)


def main():
    """Main entry point."""
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Generate dump
    print("📊 Dumping database tables...")
    dump_content = dump_all_tables()

    # Write to log file with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = DATA_DIR / f"database_dump_{timestamp}.log"

    print(f"💾 Writing to {log_file}...")
    log_file.write_text(dump_content, encoding="utf-8")

    print(f"✅ Database dump complete: {log_file}")
    print(f"   File size: {log_file.stat().st_size / 1024:.2f} KB")


if __name__ == "__main__":
    main()
