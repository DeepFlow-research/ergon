"""
tests/utils/assertions.py

Reusable assertion functions for E2E and deterministic PG-state tests.

Uses the simplified schema where Action.error and CriterionResult.error
are either None (success) or an ExecutionError dict.
"""

import json
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from h_arcane.core._internal.db.models import (
    Experiment,
    Run,
    RunStatus,
    Action,
    CriterionResult,
    Evaluation,
    ResourceRecord,
    TaskExecution,
    TaskEvaluator,
    TaskStateEvent,
    Thread,
    ThreadMessage,
)
from h_arcane.core._internal.db.queries import queries
from h_arcane.core.status import TaskStatus


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
    evaluation = session.exec(select(Evaluation).where(Evaluation.run_id == run.id)).first()

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
# Deterministic PG Snapshot Helpers
# ============================================================================


class RunStateSnapshot(BaseModel):
    """Complete persisted state for one deterministic benchmark run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    experiment: Experiment
    run: Run
    actions: list[Action] = Field(default_factory=list)
    resources: list[ResourceRecord] = Field(default_factory=list)
    evaluation: Evaluation | None = None
    criterion_results: list[CriterionResult] = Field(default_factory=list)
    task_executions: list[TaskExecution] = Field(default_factory=list)
    task_state_events: list[TaskStateEvent] = Field(default_factory=list)
    task_evaluators: list[TaskEvaluator] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list)
    thread_messages: list[ThreadMessage] = Field(default_factory=list)


def load_run_state_snapshot(run_id: UUID) -> RunStateSnapshot:
    """Load the persisted state for one run using shared query helpers."""
    run = queries.runs.get(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        raise ValueError(f"Experiment {run.experiment_id} not found")

    threads = queries.threads.get_threads_between_agents(
        f"{run_id}:worker",
        f"{run_id}:stakeholder",
    )
    thread_messages: list[ThreadMessage] = []
    for thread in threads:
        thread_messages.extend(queries.thread_messages.get_by_thread(thread.id))

    return RunStateSnapshot(
        experiment=experiment,
        run=run,
        actions=queries.actions.get_all(run_id, order_by="action_num"),
        resources=queries.resources.get_by_experiment(experiment.id)
        + queries.resources.get_by_run(run_id),
        evaluation=queries.evaluations.get_by_run(run_id),
        criterion_results=queries.criterion_results.get_all(run_id, order_by="stage_num"),
        task_executions=queries.task_executions.get_by_run(run_id),
        task_state_events=queries.task_state_events.get_by_run(run_id),
        task_evaluators=queries.task_evaluators.get_by_run(run_id),
        threads=threads,
        thread_messages=thread_messages,
    )


def _action_inputs(snapshot: RunStateSnapshot) -> list[dict]:
    return [json.loads(action.input) for action in snapshot.actions]


def assert_minif2f_two_pass_case(snapshot: RunStateSnapshot) -> None:
    """Assert the MiniF2F golden case persisted the expected state."""
    assert snapshot.experiment.benchmark_name.value == "minif2f"
    assert snapshot.run.status == RunStatus.COMPLETED
    assert snapshot.run.error_message is None
    assert snapshot.run.e2b_sandbox_id is None
    assert snapshot.run.started_at is not None
    assert snapshot.run.completed_at is not None
    assert snapshot.run.completed_at >= snapshot.run.started_at
    assert snapshot.run.questions_asked == 1
    assert snapshot.run.total_cost_usd == 0.0

    action_names = [action.action_type for action in snapshot.actions]
    assert action_names == [
        "ask_stakeholder",
        "write_lean_file",
        "check_lean_file",
        "search_lemmas",
        "write_lean_file",
        "verify_lean_proof",
    ]

    for action in snapshot.actions:
        assert action.started_at is not None
        assert action.completed_at is not None
        assert action.completed_at >= action.started_at
        assert action.duration_ms is not None
        assert action.agent_total_tokens == 0
        assert action.agent_total_cost_usd == 0.0

    inputs = _action_inputs(snapshot)
    assert inputs[0]["question"] == "Should I prefer a short direct proof if one exists?"
    assert inputs[1]["file_path"] == "/workspace/scratchpad/solution.lean"
    assert "sorry" in inputs[1]["content"]
    assert inputs[2]["file_path"] == "/workspace/scratchpad/solution.lean"
    assert "nat.add_zero" in inputs[3]["query"]
    assert inputs[4]["file_path"] == "/workspace/final_output/final_solution.lean"
    assert "sorry" not in inputs[4]["content"]
    assert inputs[5]["file_path"] == "/workspace/final_output/final_solution.lean"

    assert "short direct proof" in (snapshot.actions[0].output or "").lower()
    assert '"compiled": true' in (snapshot.actions[2].output or "").lower()
    assert '"verified": true' in (snapshot.actions[5].output or "").lower()

    output_resources = [resource for resource in snapshot.resources if resource.run_id == snapshot.run.id]
    assert len(output_resources) == 1
    assert output_resources[0].name == "final_solution.lean"

    assert len(snapshot.threads) == 1
    assert len(snapshot.thread_messages) == 2
    assert snapshot.thread_messages[0].content == inputs[0]["question"]
    assert "short direct proof" in snapshot.thread_messages[1].content.lower()

    assert snapshot.evaluation is not None
    assert snapshot.evaluation.total_score == 1.0
    assert snapshot.evaluation.normalized_score == 1.0
    assert len(snapshot.criterion_results) == 1
    assert snapshot.criterion_results[0].score == 1.0

    assert len(snapshot.task_executions) == 1
    assert snapshot.task_executions[0].status == TaskStatus.COMPLETED
    assert len(snapshot.task_evaluators) == 1
    assert snapshot.task_evaluators[0].status.value == "completed"


def assert_researchrubrics_search_synthesize_case(snapshot: RunStateSnapshot) -> None:
    """Assert the ResearchRubrics golden case persisted the expected state."""
    assert snapshot.experiment.benchmark_name.value == "researchrubrics"
    assert snapshot.run.status == RunStatus.COMPLETED
    assert snapshot.run.error_message is None
    assert snapshot.run.e2b_sandbox_id is None
    assert snapshot.run.started_at is not None
    assert snapshot.run.completed_at is not None
    assert snapshot.run.completed_at >= snapshot.run.started_at
    assert snapshot.run.questions_asked == 1
    assert snapshot.run.total_cost_usd == 0.0

    action_names = [action.action_type for action in snapshot.actions]
    assert action_names == [
        "ask_stakeholder_tool",
        "exa_search_tool",
        "exa_qa_tool",
        "exa_get_content_tool",
        "exa_get_content_tool",
        "write_report_draft_tool",
        "edit_report_draft_tool",
        "read_report_draft_tool",
    ]

    for action in snapshot.actions:
        assert action.started_at is not None
        assert action.completed_at is not None
        assert action.completed_at >= action.started_at
        assert action.duration_ms is not None
        assert action.agent_total_tokens == 0
        assert action.agent_total_cost_usd == 0.0

    inputs = _action_inputs(snapshot)
    assert inputs[0]["question"] == "Should I prioritize risks or opportunities in the report?"
    assert "AI chip supply chain concentration risks" in inputs[1]["query"]
    assert "main risks" in inputs[2]["question"]
    assert inputs[3]["url"] == "https://example.com/source-1"
    assert inputs[4]["url"] == "https://example.com/source-2"
    assert inputs[5]["file_path"] == "/workspace/final_output/report.md"
    assert inputs[6]["old_string"] == "Initial draft:"
    assert inputs[6]["new_string"] == "Revised synthesis:"
    assert inputs[7]["file_path"] == "/workspace/final_output/report.md"

    assert "prioritize risks" in (snapshot.actions[0].output or "").lower()
    assert '"success": true' in (snapshot.actions[1].output or "").lower()
    assert '"success": true' in (snapshot.actions[2].output or "").lower()
    assert '"success": true' in (snapshot.actions[3].output or "").lower()
    assert '"success": true' in (snapshot.actions[4].output or "").lower()
    assert "revised synthesis" in (snapshot.actions[7].output or "").lower()

    output_resources = [resource for resource in snapshot.resources if resource.run_id == snapshot.run.id]
    assert len(output_resources) == 1
    assert output_resources[0].name == "report.md"
    assert "Revised synthesis:" in output_resources[0].load_text()

    assert len(snapshot.threads) == 1
    assert len(snapshot.thread_messages) == 2
    assert snapshot.thread_messages[0].content == inputs[0]["question"]
    assert "prioritize risks" in snapshot.thread_messages[1].content.lower()

    assert snapshot.evaluation is not None
    assert snapshot.evaluation.total_score == 1.0
    assert snapshot.evaluation.normalized_score == 1.0
    assert len(snapshot.criterion_results) == 2
    assert all(result.score > 0 for result in snapshot.criterion_results)

    assert len(snapshot.task_executions) == 1
    assert snapshot.task_executions[0].output_text is not None
    assert len(snapshot.task_evaluators) == 1
    assert snapshot.task_evaluators[0].status.value == "completed"


# ============================================================================
# Assertion Functions
# ============================================================================


def assert_run_completed(run: Run, session: Session):
    """Assert run reached COMPLETED status."""
    assert run.status == RunStatus.COMPLETED, f"Run failed with status {run.status}"


def assert_evaluation_ran(run: Run, session: Session):
    """Assert evaluation was executed and produced scores."""
    evaluation = session.exec(select(Evaluation).where(Evaluation.run_id == run.id)).first()

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
