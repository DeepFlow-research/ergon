"""Full-lifecycle integration test driven through real Inngest + real Postgres.

Previous incarnation of this file called service classes directly and
skipped ``inngest_client.send``. That produced "service-class correctness"
signal, not "durable event-flow correctness" signal — the two are not
interchangeable. Per ``docs/architecture/07_testing.md`` §7 and the
posture-reset RFC (``docs/rfcs/active/2026-04-18-testing-posture-reset.md``),
the integration tier drives the exact production code path: dispatch a
``WorkflowStartedEvent`` via ``inngest_client.send``, let the Inngest dev
server durably route it through every registered function, and assert on
post-processing state via ORM reads.

Requires the CI / local docker stack to be up (``docker-compose.ci.yml``):

    docker compose -f docker-compose.ci.yml up -d --build --wait

Env (set by the CI job; defaults match local compose bring-up)::

    ERGON_DATABASE_URL=postgresql://ergon:ci_test@localhost:5433/ergon
    INNGEST_API_BASE_URL=http://localhost:8289
    INNGEST_DEV=1
    INNGEST_EVENT_KEY=dev
"""

from ergon_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_core.api import Experiment, WorkerSpec
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunTaskExecution,
)
from sqlmodel import select


async def test_full_lifecycle() -> None:
    """Drive a 2-task smoke experiment end-to-end through Inngest and assert graph state.

    Preserves the behavioural coverage of the bypass-flavoured predecessor:
      - ``Experiment`` composes, validates, and persists to the ``ExperimentDefinition`` row set.
      - A ``RunRecord`` is created and its dispatching event (``workflow/started``)
        is routed by Inngest through the worker-execute / propagate / finalize chain.
      - The terminal state written by the production code path matches the contract:
        run is ``COMPLETED``; every task execution is ``COMPLETED`` with a persisted
        ``final_assistant_message``.
    """
    # ── Ensure schema is migrated (idempotent) ─────────────────────────
    # The API container ships without the migrations directory, so it skips
    # the upgrade on startup (see ``db.ensure_db``). Running from the host,
    # the directory is present; calling here applies any pending head.
    ensure_db()

    # ── Compose + validate + persist ────────────────────────────────────
    benchmark = SmokeTestBenchmark(workflow="flat", task_count=2)
    # reason: RFC 2026-04-22 §1 — ``Experiment`` holds ``WorkerSpec`` descriptors
    # at config time; the live ``Worker`` is built per-task via the registry
    # factory inside the ``worker_execute`` Inngest fn.
    spec = WorkerSpec(worker_slug="stub-worker", name="test", model="openai:gpt-4o")
    rubric = StubRubric()

    experiment = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=spec,
        evaluators={"default": rubric},
    )

    # ── Dispatch via Inngest and block on terminal state ────────────────
    # ``Experiment.run()`` calls ``create_experiment_run`` which:
    #   1. Inserts a ``RunRecord`` (status=PENDING).
    #   2. Calls ``inngest_client.send(WorkflowStartedEvent(...))`` — the
    #      single dispatch seam that the posture-reset RFC requires tests
    #      to go through.
    #   3. Polls ``RunRecord.status`` every second until it reaches a
    #      terminal status or the timeout elapses.
    # Assertions below run against whatever the production Inngest
    # functions wrote, not against return values from in-process service
    # calls.
    handle = await experiment.run()

    assert handle.status == RunStatus.COMPLETED, (
        f"Expected run {handle.run_id} to reach COMPLETED via Inngest, "
        f"got {handle.status!r}. Check `docker compose logs api inngest-dev`."
    )

    # ── Verify persisted state matches the terminal contract ────────────
    with get_session() as session:
        # Definition round-tripped and owns exactly 2 task rows.
        defn = session.get(ExperimentDefinition, handle.definition_id)
        assert defn is not None
        assert defn.benchmark_type == "smoke-test"
        task_rows = list(
            session.exec(
                select(ExperimentDefinitionTask).where(
                    ExperimentDefinitionTask.experiment_definition_id == handle.definition_id
                )
            ).all()
        )
        assert len(task_rows) == 2

        # RunRecord is COMPLETED — the terminal status Inngest's finalize fn writes.
        run_row = session.get(RunRecord, handle.run_id)
        assert run_row is not None
        assert run_row.status == RunStatus.COMPLETED

        # Every task execution reached COMPLETED and produced output.
        executions = list(
            session.exec(
                select(RunTaskExecution).where(RunTaskExecution.run_id == handle.run_id)
            ).all()
        )
        assert len(executions) == 2, f"Expected 2 task executions, got {len(executions)}"
        for execution in executions:
            assert execution.status == TaskExecutionStatus.COMPLETED
            assert execution.final_assistant_message is not None
            assert execution.completed_at is not None
