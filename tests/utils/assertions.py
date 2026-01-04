"""
tests/utils/assertions.py

Reusable assertion functions for E2E tests.

Uses the simplified schema where Action.error and CriterionResult.error
are either None (success) or an ExecutionError dict.
"""

from dataclasses import dataclass

from sqlmodel import Session, select

from h_arcane.core.db.models import (
    Run,
    RunStatus,
    Action,
    CriterionResult,
    Evaluation,
)


@dataclass
class RunResult:
    """Result of checking a run - all failures flagged for review."""

    run_status: RunStatus
    failed_actions: list[Action]
    failed_evals: list[CriterionResult]
    has_evaluation: bool
    has_scores: bool

    @property
    def completed(self) -> bool:
        return self.run_status == RunStatus.COMPLETED

    def print_failures(self, show_stack_traces: bool = True):
        """Print all failures for manual review."""
        if self.failed_actions:
            print(f"\n⚠️  FAILED ACTIONS ({len(self.failed_actions)}):")
            for a in self.failed_actions:
                print(f"\n  [{a.action_type}]")
                error = a.get_error()
                if error:
                    print(f"    message: {error.message}")
                    if error.exception_type:
                        print(f"    exception: {error.exception_type}")
                    if show_stack_traces and error.stack_trace:
                        print("    stack trace:")
                        # Indent each line of stack trace
                        for line in error.stack_trace.strip().split("\n"):
                            print(f"      {line}")
                else:
                    print("    message: unknown error")

        if self.failed_evals:
            print(f"\n⚠️  FAILED EVALUATIONS ({len(self.failed_evals)}):")
            for cr in self.failed_evals:
                print(f"\n  [{cr.criterion_description}]")
                error = cr.get_error()
                if error:
                    print(f"    message: {error.message}")
                    if show_stack_traces and error.stack_trace:
                        print("    stack trace:")
                        for line in error.stack_trace.strip().split("\n"):
                            print(f"      {line}")
                else:
                    print("    message: unknown error")


def check_run(run: Run, session: Session) -> RunResult:
    """
    Check run state and return result with all failures.

    No automatic classification - just collects failures for manual review.
    """
    # Get all actions
    actions = session.exec(select(Action).where(Action.run_id == run.id)).all()

    # Any action with error is a failure
    failed_actions = [a for a in actions if not a.success]

    # Get criterion results
    criterion_results = session.exec(
        select(CriterionResult).where(CriterionResult.run_id == run.id)
    ).all()

    failed_evals = [cr for cr in criterion_results if not cr.ran_successfully]

    # Check evaluation exists
    evaluation = session.exec(
        select(Evaluation).where(Evaluation.run_id == run.id)
    ).first()

    has_evaluation = evaluation is not None
    has_scores = (
        evaluation is not None
        and evaluation.total_score is not None
        and run.final_score is not None
    )

    return RunResult(
        run_status=run.status,
        failed_actions=failed_actions,
        failed_evals=failed_evals,
        has_evaluation=has_evaluation,
        has_scores=has_scores,
    )


# ============================================================================
# Assertion Functions
# ============================================================================


def assert_run_completed(run: Run, session: Session):
    """Assert run reached COMPLETED status."""
    assert run.status == RunStatus.COMPLETED, f"Run failed with status {run.status}"


def assert_evaluation_ran(run: Run, session: Session):
    """Assert evaluation was executed and produced scores."""
    evaluation = session.exec(
        select(Evaluation).where(Evaluation.run_id == run.id)
    ).first()

    assert evaluation is not None, "No Evaluation record created"
    assert evaluation.total_score is not None, "Evaluation missing total_score"

    criterion_results = session.exec(
        select(CriterionResult).where(CriterionResult.run_id == run.id)
    ).all()

    assert len(criterion_results) > 0, "No CriterionResult records - evaluation didn't run"


def assert_run_completed_and_print_failures(run: Run, session: Session):
    """
    Assert run completed, print any failures for manual review.

    Does NOT fail on tool errors - just prints them.
    The human reviews the output to decide if failures are concerning.
    """
    result = check_run(run, session)

    # Always print failures for review
    result.print_failures()

    # Only assert on completion and evaluation
    assert result.completed, f"Run failed with status {result.run_status}"
    assert result.has_evaluation, "No Evaluation record created"
    assert result.has_scores, "Missing scores"

