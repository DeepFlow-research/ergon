"""Dump test database tables to understand E2E test failures.

Similar to dump_database.py but:
- Uses the TEST database (h_arcane_test or main DB based on E2E config)
- Highlights failures prominently
- Shows error details and stack traces
- Focuses on debugging test issues

Usage:
    python scripts/dump_test_database.py
    python scripts/dump_test_database.py --failures-only
    python scripts/dump_test_database.py -b gdpeval

Output:
    Creates a timestamped log file:
    data/test_db_dump_YYYYMMDD_HHMMSS.log
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, create_engine, select

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.settings import settings
from h_arcane.core.db.models import (
    Action,
    AgentConfig,
    CriterionResult,
    Evaluation,
    Experiment,
    Message,
    Resource,
    Run,
    RunStatus,
    TaskEvaluationResult,
    Thread,
    ThreadMessage,
)

# Output directory for dumps
DATA_DIR = Path(__file__).parent.parent / "data"


def get_test_db_engine():
    """Get engine for test database (uses main DB by default, like E2E tests)."""
    import os
    
    use_test_db = os.environ.get("E2E_USE_TEST_DB", "").lower() in ("1", "true", "yes")
    
    if use_test_db:
        db_url = settings.database_url_test
        print(f"🔧 Using TEST database: {db_url}")
    else:
        db_url = settings.database_url
        print(f"🔧 Using MAIN database: {db_url}")
    
    return create_engine(db_url, pool_pre_ping=True)


def format_value(value, max_length: int = 500):
    """Format a value for readable output."""
    if value is None:
        return "NULL"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        formatted = json.dumps(value, indent=2, default=str)
        if len(formatted) > max_length:
            return formatted[:max_length] + f"\n... (truncated, total: {len(formatted)} chars)"
        return formatted
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + f"\n... (truncated, total: {len(value)} chars)"
    return str(value)


def format_error_details(action_or_criterion) -> str:
    """Format error details prominently."""
    error = action_or_criterion.get_error() if hasattr(action_or_criterion, 'get_error') else None
    if not error:
        # Try getting from error field directly
        error_data = getattr(action_or_criterion, 'error', None)
        if error_data and isinstance(error_data, dict):
            lines = ["    🔴 ERROR:"]
            lines.append(f"       message: {error_data.get('message', 'Unknown')}")
            if error_data.get('exception_type'):
                lines.append(f"       type: {error_data['exception_type']}")
            if error_data.get('stack_trace'):
                lines.append("       stack trace:")
                for line in error_data['stack_trace'].strip().split('\n'):
                    lines.append(f"         {line}")
            return '\n'.join(lines)
        return ""
    
    lines = ["    🔴 ERROR:"]
    lines.append(f"       message: {error.message}")
    if error.exception_type:
        lines.append(f"       type: {error.exception_type}")
    if error.stack_trace:
        lines.append("       stack trace:")
        for line in error.stack_trace.strip().split('\n'):
            lines.append(f"         {line}")
    return '\n'.join(lines)


# =============================================================================
# Dump Functions
# =============================================================================

def dump_summary(session: Session, benchmark: BenchmarkName | None) -> str:
    """Generate summary section with failure counts."""
    lines = []
    
    # Get experiments
    exp_stmt = select(Experiment)
    if benchmark:
        exp_stmt = exp_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(exp_stmt).all())
    exp_ids = {e.id for e in experiments}
    
    # Get runs
    if exp_ids:
        runs = list(session.exec(select(Run).where(Run.experiment_id.in_(exp_ids))).all())  # type: ignore
    else:
        runs = list(session.exec(select(Run)).all()) if not benchmark else []
    run_ids = {r.id for r in runs}
    
    # Count run statuses
    status_counts = {}
    for run in runs:
        status = run.status.value if run.status else "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Get failed actions
    if run_ids:
        actions = list(session.exec(select(Action).where(Action.run_id.in_(run_ids))).all())  # type: ignore
    else:
        actions = []
    failed_actions = [a for a in actions if not a.success]
    
    # Get failed evaluations
    if run_ids:
        criteria = list(session.exec(select(CriterionResult).where(CriterionResult.run_id.in_(run_ids))).all())  # type: ignore
    else:
        criteria = []
    failed_criteria = [c for c in criteria if not c.ran_successfully]
    
    lines.append("\n" + "=" * 80)
    lines.append("📊 TEST DATABASE SUMMARY")
    lines.append("=" * 80)
    
    lines.append(f"\n🧪 Experiments: {len(experiments)}")
    lines.append(f"🏃 Runs: {len(runs)}")
    for status, count in sorted(status_counts.items()):
        emoji = "✅" if status == "COMPLETED" else "❌" if status == "FAILED" else "⏳"
        lines.append(f"   {emoji} {status}: {count}")
    
    lines.append(f"\n🔧 Actions: {len(actions)}")
    if failed_actions:
        lines.append(f"   ❌ Failed: {len(failed_actions)}")
    
    lines.append(f"\n📋 Criterion Results: {len(criteria)}")
    if failed_criteria:
        lines.append(f"   ❌ Failed: {len(failed_criteria)}")
    
    if failed_actions or failed_criteria or any(r.status == RunStatus.FAILED for r in runs):
        lines.append("\n" + "⚠️ " * 20)
        lines.append("FAILURES DETECTED - See details below")
        lines.append("⚠️ " * 20)
    else:
        lines.append("\n" + "✅ " * 20)
        lines.append("ALL TESTS PASSED")
        lines.append("✅ " * 20)
    
    return '\n'.join(lines)


def dump_failed_runs(session: Session, benchmark: BenchmarkName | None) -> str:
    """Dump details of failed runs."""
    lines = []
    
    # Get experiments
    exp_stmt = select(Experiment)
    if benchmark:
        exp_stmt = exp_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(exp_stmt).all())
    exp_map = {e.id: e for e in experiments}
    exp_ids = set(exp_map.keys())
    
    # Get failed runs
    if exp_ids:
        failed_runs = list(session.exec(
            select(Run)
            .where(Run.experiment_id.in_(exp_ids))  # type: ignore
            .where(Run.status == RunStatus.FAILED)
        ).all())
    else:
        failed_runs = list(session.exec(select(Run).where(Run.status == RunStatus.FAILED)).all()) if not benchmark else []
    
    if not failed_runs:
        return ""
    
    lines.append("\n" + "=" * 80)
    lines.append(f"❌ FAILED RUNS ({len(failed_runs)})")
    lines.append("=" * 80)
    
    for run in failed_runs:
        exp = exp_map.get(run.experiment_id)
        lines.append(f"\n--- Run {run.id} ---")
        lines.append(f"  experiment_id: {run.experiment_id}")
        lines.append(f"  benchmark: {exp.benchmark_name.value if exp else 'UNKNOWN'}")
        lines.append(f"  task_id: {exp.task_id if exp else 'UNKNOWN'}")
        lines.append(f"  status: {run.status.value}")
        lines.append(f"  error_message: {run.error_message or 'NULL'}")
        lines.append(f"  created_at: {run.created_at}")
        lines.append(f"  completed_at: {run.completed_at or 'NULL'}")
    
    return '\n'.join(lines)


def dump_failed_actions(session: Session, benchmark: BenchmarkName | None) -> str:
    """Dump details of failed actions with stack traces."""
    lines = []
    
    # Get experiments
    exp_stmt = select(Experiment)
    if benchmark:
        exp_stmt = exp_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(exp_stmt).all())
    exp_ids = {e.id for e in experiments}
    
    # Get runs
    if exp_ids:
        runs = list(session.exec(select(Run).where(Run.experiment_id.in_(exp_ids))).all())  # type: ignore
    else:
        runs = list(session.exec(select(Run)).all()) if not benchmark else []
    run_ids = {r.id for r in runs}
    run_map = {r.id: r for r in runs}
    
    # Get failed actions
    if run_ids:
        failed_actions = list(session.exec(
            select(Action)
            .where(Action.run_id.in_(run_ids))  # type: ignore
            .where(Action.error.isnot(None))  # type: ignore
        ).all())
    else:
        failed_actions = []
    
    if not failed_actions:
        return ""
    
    lines.append("\n" + "=" * 80)
    lines.append(f"❌ FAILED ACTIONS ({len(failed_actions)})")
    lines.append("=" * 80)
    
    for action in failed_actions:
        run = run_map.get(action.run_id)
        lines.append(f"\n--- Action {action.id} ---")
        lines.append(f"  run_id: {action.run_id}")
        lines.append(f"  action_type: {action.action_type}")
        lines.append(f"  tool_name: {action.tool_name or 'NULL'}")
        lines.append(f"  created_at: {action.created_at}")
        
        # Show input (truncated)
        if action.tool_input:
            input_str = format_value(action.tool_input, max_length=300)
            lines.append(f"  input: {input_str}")
        
        # Show error details prominently
        error_details = format_error_details(action)
        if error_details:
            lines.append(error_details)
    
    return '\n'.join(lines)


def dump_failed_evaluations(session: Session, benchmark: BenchmarkName | None) -> str:
    """Dump details of failed criterion evaluations."""
    lines = []
    
    # Get experiments
    exp_stmt = select(Experiment)
    if benchmark:
        exp_stmt = exp_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(exp_stmt).all())
    exp_ids = {e.id for e in experiments}
    
    # Get runs
    if exp_ids:
        runs = list(session.exec(select(Run).where(Run.experiment_id.in_(exp_ids))).all())  # type: ignore
    else:
        runs = list(session.exec(select(Run)).all()) if not benchmark else []
    run_ids = {r.id for r in runs}
    
    # Get failed criterion results
    if run_ids:
        failed_criteria = list(session.exec(
            select(CriterionResult)
            .where(CriterionResult.run_id.in_(run_ids))  # type: ignore
            .where(CriterionResult.error.isnot(None))  # type: ignore
        ).all())
    else:
        failed_criteria = []
    
    if not failed_criteria:
        return ""
    
    lines.append("\n" + "=" * 80)
    lines.append(f"❌ FAILED EVALUATIONS ({len(failed_criteria)})")
    lines.append("=" * 80)
    
    for cr in failed_criteria:
        lines.append(f"\n--- CriterionResult {cr.id} ---")
        lines.append(f"  run_id: {cr.run_id}")
        lines.append(f"  criterion: {cr.criterion_description[:100] if cr.criterion_description else 'NULL'}...")
        
        error_details = format_error_details(cr)
        if error_details:
            lines.append(error_details)
    
    return '\n'.join(lines)


def dump_all_runs(session: Session, benchmark: BenchmarkName | None) -> str:
    """Dump all runs with their scores."""
    lines = []
    
    # Get experiments
    exp_stmt = select(Experiment)
    if benchmark:
        exp_stmt = exp_stmt.where(Experiment.benchmark_name == benchmark)
    experiments = list(session.exec(exp_stmt).all())
    exp_map = {e.id: e for e in experiments}
    exp_ids = set(exp_map.keys())
    
    # Get all runs
    if exp_ids:
        runs = list(session.exec(select(Run).where(Run.experiment_id.in_(exp_ids))).all())  # type: ignore
    else:
        runs = list(session.exec(select(Run)).all()) if not benchmark else []
    
    if not runs:
        return "\n(No runs found)\n"
    
    lines.append("\n" + "=" * 80)
    lines.append(f"📋 ALL RUNS ({len(runs)})")
    lines.append("=" * 80)
    
    for run in runs:
        exp = exp_map.get(run.experiment_id)
        status_emoji = "✅" if run.status == RunStatus.COMPLETED else "❌" if run.status == RunStatus.FAILED else "⏳"
        
        lines.append(f"\n{status_emoji} Run {run.id}")
        lines.append(f"   benchmark: {exp.benchmark_name.value if exp else 'UNKNOWN'}")
        lines.append(f"   task_id: {exp.task_id if exp else 'UNKNOWN'}")
        lines.append(f"   status: {run.status.value}")
        lines.append(f"   final_score: {run.final_score if run.final_score is not None else 'NULL'}")
        lines.append(f"   questions_asked: {run.questions_asked if run.questions_asked is not None else 'NULL'}")
        if run.error_message:
            lines.append(f"   error: {run.error_message}")
    
    return '\n'.join(lines)


def dump_test_database(
    benchmark: BenchmarkName | None = None,
    failures_only: bool = False,
) -> str:
    """Dump test database to a formatted string."""
    output = []
    output.append("=" * 80)
    output.append("TEST DATABASE DUMP")
    output.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    if benchmark:
        output.append(f"Benchmark filter: {benchmark.value}")
    output.append(f"Mode: {'FAILURES ONLY' if failures_only else 'FULL'}")
    output.append("=" * 80)
    
    engine = get_test_db_engine()
    
    with Session(engine) as session:
        # Always show summary
        output.append(dump_summary(session, benchmark))
        
        # Always show failures
        output.append(dump_failed_runs(session, benchmark))
        output.append(dump_failed_actions(session, benchmark))
        output.append(dump_failed_evaluations(session, benchmark))
        
        # Show all runs unless failures_only
        if not failures_only:
            output.append(dump_all_runs(session, benchmark))
    
    return '\n'.join(output)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Dump test database to understand E2E test failures.",
    )
    parser.add_argument(
        "-b", "--benchmark",
        type=str,
        choices=[b.value for b in BenchmarkName],
        help="Filter by benchmark",
    )
    parser.add_argument(
        "-f", "--failures-only",
        action="store_true",
        help="Only show failures (skip full run listing)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file path (default: auto-generated in data/)",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    benchmark: BenchmarkName | None = None
    if args.benchmark:
        benchmark = BenchmarkName(args.benchmark)
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    benchmark_label = benchmark.value if benchmark else "all"
    print(f"📊 Dumping test database (benchmark: {benchmark_label})...")
    
    dump_content = dump_test_database(
        benchmark=benchmark,
        failures_only=args.failures_only,
    )
    
    # Determine output file
    if args.output:
        log_file = Path(args.output)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = f"_{benchmark.value}" if benchmark else ""
        log_file = DATA_DIR / f"test_db_dump{suffix}_{timestamp}.log"
    
    print(f"💾 Writing to {log_file}...")
    log_file.write_text(dump_content, encoding="utf-8")
    
    print(f"✅ Test database dump complete: {log_file}")
    print(f"   File size: {log_file.stat().st_size / 1024:.2f} KB")
    
    # Also print summary to console
    print("\n" + "=" * 60)
    print("QUICK SUMMARY:")
    print("=" * 60)
    engine = get_test_db_engine()
    with Session(engine) as session:
        print(dump_summary(session, benchmark))


if __name__ == "__main__":
    main()

