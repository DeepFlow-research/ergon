"""Dump all database tables to a formatted log file for LLM consumption.

LLM UTILITY: This script exports all database tables to a human-readable log file
that can be easily consumed by LLMs (like Copilot) to understand experiment results
and debug issues.

Usage:
    python scripts/dump_database.py
    python scripts/dump_database.py --benchmark gdpeval
    python scripts/dump_database.py -b minif2f

    Or:
    python -m scripts.dump_database
    python -m scripts.dump_database --benchmark researchrubrics

Output:
    Creates a timestamped log file in the data directory:
    data/database_dump_YYYYMMDD_HHMMSS.log
    data/database_dump_gdpeval_YYYYMMDD_HHMMSS.log (with benchmark filter)

The log file contains:
    - Summary statistics (row counts per table)
    - All data from all 11 tables formatted for readability:
      * experiments: Tasks with ground truth rubrics
      * runs: Experiment execution runs
      * messages: Worker-stakeholder conversation history
      * actions: Tool execution traces
      * resources: Input/output files
      * agent_configs: Agent configuration snapshots
      * evaluations: Aggregate evaluation results
      * criterion_results: Per-criterion evaluation scores
      * task_evaluation_results: Complete evaluation snapshots
      * threads: Communication threads between agents
      * thread_messages: Messages within threads

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

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core._internal.db.connection import get_session
from h_arcane.core._internal.db.models import (
    Action,
    AgentConfig,
    CriterionResult,
    Evaluation,
    Experiment,
    Message,
    ResourceRecord,
    Run,
    TaskEvaluationResult,
    Thread,
    ThreadMessage,
)

# Output directory for dumps
DATA_DIR = Path(__file__).parent.parent / "data"


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


def dump_table(session: Session, model_class, table_name: str, rows: list) -> str:
    """Dump rows from a table."""
    if not rows:
        return format_table_header(table_name, 0) + "\n(No rows)\n"

    output = [format_table_header(table_name, len(rows))]

    for i, row in enumerate(rows, 1):
        row_dict = row.model_dump(mode="json")
        output.append(format_row(row_dict, i))

    return "\n".join(output) + "\n"


def get_filtered_data(
    session: Session,
    benchmark: BenchmarkName | None,
) -> dict[str, list]:
    """Get all table data, optionally filtered by benchmark.

    Returns a dict mapping table name to list of rows.
    """
    data = {}

    # Get experiments (filtered by benchmark if specified)
    experiment_stmt = select(Experiment)
    if benchmark:
        experiment_stmt = experiment_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(experiment_stmt).all())
    data["experiments"] = experiments

    # Get experiment IDs for filtering child tables
    experiment_ids = {exp.id for exp in experiments}

    # Get runs (filtered by experiment_ids)
    if experiment_ids:
        run_stmt = select(Run).where(Run.experiment_id.in_(experiment_ids))  # type: ignore[union-attr]
        runs = list(session.exec(run_stmt).all())
    else:
        runs = [] if benchmark else list(session.exec(select(Run)).all())
    data["runs"] = runs

    # Get run IDs for filtering child tables
    run_ids = {run.id for run in runs}

    # Tables that reference run_id
    run_child_tables = [
        (Message, "messages"),
        (Action, "actions"),
        (AgentConfig, "agent_configs"),
        (Evaluation, "evaluations"),
        (CriterionResult, "criterion_results"),
        (TaskEvaluationResult, "task_evaluation_results"),
        (Thread, "threads"),
        (ThreadMessage, "thread_messages"),
    ]

    for model_class, table_name in run_child_tables:
        if run_ids:
            stmt = select(model_class).where(model_class.run_id.in_(run_ids))  # type: ignore[union-attr]
            rows = list(session.exec(stmt).all())
        else:
            rows = [] if benchmark else list(session.exec(select(model_class)).all())
        data[table_name] = rows

    # Resources can belong to experiments OR runs
    if benchmark:
        resource_rows = []
        if experiment_ids:
            exp_resources = list(
                session.exec(
                    select(ResourceRecord).where(ResourceRecord.experiment_id.in_(experiment_ids))  # type: ignore[union-attr]
                ).all()
            )
            resource_rows.extend(exp_resources)
        if run_ids:
            run_resources = list(
                session.exec(
                    select(ResourceRecord).where(ResourceRecord.run_id.in_(run_ids))  # type: ignore[union-attr]
                ).all()
            )
            resource_rows.extend(run_resources)
        # Deduplicate by ID
        seen_ids = set()
        unique_resources = []
        for r in resource_rows:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                unique_resources.append(r)
        data["resources"] = unique_resources
    else:
        data["resources"] = list(session.exec(select(ResourceRecord)).all())

    return data


def get_table_counts(data: dict[str, list]) -> dict[str, int]:
    """Get row counts for all tables from pre-fetched data."""
    return {table_name: len(rows) for table_name, rows in data.items()}


def dump_all_tables(benchmark: BenchmarkName | None = None) -> str:
    """Dump all tables to a formatted string."""
    output = []
    output.append("=" * 80)
    output.append("DATABASE DUMP")
    output.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    if benchmark:
        output.append(f"Benchmark filter: {benchmark.value}")
    else:
        output.append("Benchmark filter: ALL")
    output.append("=" * 80)

    with next(get_session()) as session:
        # Get all data (filtered by benchmark if specified)
        data = get_filtered_data(session, benchmark)

        # Get summary counts
        counts = get_table_counts(data)
        output.append("\nSUMMARY:")
        output.append("-" * 80)
        for table_name, count in sorted(counts.items()):
            output.append(f"  {table_name:30} {count:>10} rows")
        output.append("-" * 80)

        # Define tables in logical order (parent tables first)
        table_order = [
            "experiments",
            "runs",
            "messages",
            "actions",
            "resources",
            "agent_configs",
            "evaluations",
            "criterion_results",
            "task_evaluation_results",
            "threads",
            "thread_messages",
        ]

        # Model classes for formatting
        model_map = {
            "experiments": Experiment,
            "runs": Run,
            "messages": Message,
            "actions": Action,
            "resources": ResourceRecord,
            "agent_configs": AgentConfig,
            "evaluations": Evaluation,
            "criterion_results": CriterionResult,
            "task_evaluation_results": TaskEvaluationResult,
            "threads": Thread,
            "thread_messages": ThreadMessage,
        }

        for table_name in table_order:
            try:
                rows = data.get(table_name, [])
                model_class = model_map[table_name]
                table_output = dump_table(session, model_class, table_name, rows)
                output.append(table_output)
            except Exception as e:
                output.append(f"\n{'=' * 80}\nERROR dumping {table_name}: {e}\n{'=' * 80}\n")

    return "\n".join(output)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Dump database tables to a log file for LLM consumption.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/dump_database.py                    # Dump all benchmarks
  python scripts/dump_database.py -b gdpeval         # Dump only gdpeval data
  python scripts/dump_database.py --benchmark minif2f
        """,
    )
    parser.add_argument(
        "-b",
        "--benchmark",
        type=str,
        choices=[b.value for b in BenchmarkName],
        help="Filter by benchmark name (gdpeval, minif2f, researchrubrics)",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse benchmark if provided
    benchmark: BenchmarkName | None = None
    if args.benchmark:
        benchmark = BenchmarkName(args.benchmark)

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Generate dump
    benchmark_label = benchmark.value if benchmark else "all"
    print(f"📊 Dumping database tables (benchmark: {benchmark_label})...")
    dump_content = dump_all_tables(benchmark)

    # Write to log file with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if benchmark:
        log_file = DATA_DIR / f"database_dump_{benchmark.value}_{timestamp}.log"
    else:
        log_file = DATA_DIR / f"database_dump_{timestamp}.log"

    print(f"💾 Writing to {log_file}...")
    log_file.write_text(dump_content, encoding="utf-8")

    print(f"✅ Database dump complete: {log_file}")
    print(f"   File size: {log_file.stat().st_size / 1024:.2f} KB")


if __name__ == "__main__":
    main()
