"""A scripted Manager Gym episode that exercises the native runtime contract end to end.

It drives the real manager actions against a live stack (E2B, Inngest, the real
model for work roles) and records a pass/fail check per runtime guarantee. It is
a runtime contract, not a MAG score.
"""

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import ClassVar, cast
from uuid import uuid5

from ergon_builtins.benchmarks.manager_gym.actions import (
    AssignTaskAction,
    DecomposeTaskAction,
    RefineTaskAction,
    RemoveTaskAction,
)
from ergon_builtins.benchmarks.manager_gym.constants import MANAGER_ACTOR_ID
from ergon_builtins.benchmarks.manager_gym.manager import (
    assign,
    decompose_work,
    drain_admitted_work,
    refine_work,
    remove_work,
    save_message,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    apply_timeline,
    new_episode,
    project_native_state,
    snapshot_hash,
)
from ergon_builtins.benchmarks.manager_gym.upstream import (
    AIAgentConfig,
    HumanAgentConfig,
    StakeholderConfig,
    TaskStatus,
)
from ergon_builtins.benchmarks.manager_gym.upstream import Task as PlannedTask
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from pydantic import RootModel

CONTRACT_FILE = "/workspace/final_output/mag-contract.json"

# The scripted plan. The first four form a chain, each depending on the previous.
AI_NOTE = "AI note"
HUMAN_REVIEW = "Human review"
HUMAN_FOLLOW_UP = "Human follow-up"
APPROVAL = "Stakeholder approval"
REMOVED = "Remove me"
DECOMPOSED = "Decompose me"
CHAIN = (AI_NOTE, HUMAN_REVIEW, HUMAN_FOLLOW_UP, APPROVAL)
CONTRACT_TASKS = (*CHAIN, REMOVED, DECOMPOSED)
WORK_DESCRIPTION = (
    "Write a brief one-sentence work product for a simulated project status update. "
    "Use the communication send_message tool to tell manager_agent what you produced."
)


class ContractStepFailure(Worker):
    """Fails inside a durable step with a message-less error and a traceback note."""

    type_slug: ClassVar[str] = "mag-contract-step-failure"

    async def execute(self, task: Task, *, context: WorkerContext):
        async def fail() -> RootModel[str]:
            # No message on purpose: the record must fall back to the exception's name.
            error = TimeoutError()
            error.add_note("native-step-failure-proof")
            raise error

        await context.run_step("expected-step-failure", fail, output_type=RootModel[str])
        yield WorkerOutput(output="unreachable")


class ContractGate(Worker):
    """Holds its dependents pending for 30 seconds so edits and cancellation can be tested."""

    type_slug: ClassVar[str] = "mag-contract-gate"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        # Hold admission while the root proves pending mutations. Ergon owns the wait.
        await context.steps.sleep("pending-mutation-window", timedelta(seconds=30))
        yield WorkerOutput(output="gate released")


class ContractModelFailure(Worker):
    """Returns a bounded model failure, as a work role does when its request budget runs out."""

    type_slug: ClassVar[str] = "mag-contract-model-failure"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        yield WorkerOutput(
            output="Scripted worker request limit",
            success=False,
            metadata={
                "model_failure": {
                    "kind": "request_limit",
                    "message": "Scripted worker request limit",
                },
                "resources": [],
            },
        )


class CancellationContractWorker(Worker):
    """Spawns a waiting child, then tries a late spawn that sample cancellation must stop."""

    type_slug: ClassVar[str] = "mag-cancellation-contract"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        child = Task(
            task_slug="cancellation-child",
            instance_key="first",
            description="Running descendant that must stop with its sample",
            worker=ContractGate(name="Waiting child", model="test:none"),
            sandbox=E2BSandbox(timeout_seconds=600),
        )
        await context.spawn_task(child)
        await context.steps.sleep("cancel-before-late-spawn", timedelta(seconds=45))
        await context.spawn_task(child.model_copy(update={"instance_key": "late"}))
        raise RuntimeError("Sample cancellation did not stop the manager")
        yield WorkerOutput(output="unreachable")


def contract_state() -> EpisodeState:
    """An ediscovery episode whose plan is replaced by the scripted contract tasks."""
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery", seed=7))
    apply_timeline(state)
    tasks = {
        name: PlannedTask(
            id=uuid5(state.workflow.id, f"contract/{index}"),
            name=name,
            description=WORK_DESCRIPTION,
            estimated_duration_hours=1 if name == HUMAN_REVIEW else None,
        )
        for index, name in enumerate(CONTRACT_TASKS)
    }
    for prerequisite, dependent in zip(CHAIN, CHAIN[1:], strict=False):
        tasks[dependent].dependency_task_ids = [tasks[prerequisite].id]
    state.workflow.tasks = {t.id: t for t in tasks.values()}
    state.workflow.resources = {}
    for actor in state.actors.values():
        if isinstance(actor, HumanAgentConfig):
            # Guarantee two fatigue-ledger entries for the same human.
            actor.misunderstanding_rate = 0
    return state


def _first(state: EpisodeState, kind: type) -> str:
    return next(k for k in state.active_actors if isinstance(state.actors[k], kind))


class MAGContractWorker(Worker):
    """Runs the scripted contract as the manager and emits a receipt of named checks."""

    type_slug: ClassVar[str] = "mag-native-contract"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        async def initialize() -> EpisodeState:
            return contract_state()

        state = await context.run_step("contract-initialize", initialize, output_type=EpisodeState)
        plans = {t.name: t for t in state.workflow.tasks.values()}
        ai = _first(state, AIAgentConfig)
        human = _first(state, HumanAgentConfig)
        stakeholder = _first(state, StakeholderConfig)
        gate = await context.spawn_task(
            Task(
                task_slug="mag-contract-gate",
                instance_key="default",
                description="Hold pending work for edit/cancel proof",
                worker=ContractGate(name="Contract gate", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=600),
            )
        )
        state.native_dependencies[plans[AI_NOTE].id] = [gate.task_id]
        state.native_dependencies[plans[REMOVED].id] = [gate.task_id]
        assignees = {AI_NOTE: ai, HUMAN_REVIEW: human, HUMAN_FOLLOW_UP: human}
        assignees |= {APPROVAL: stakeholder, REMOVED: ai}
        for name, actor in assignees.items():
            await assign(
                state,
                AssignTaskAction(
                    reasoning="Scripted native contract",
                    task_id=str(plans[name].id),
                    agent_id=actor,
                ),
                context,
                self.model,
            )
        await refine_work(
            state,
            RefineTaskAction(
                reasoning="Prove pending Task payload replacement",
                task_id=plans[HUMAN_REVIEW].id,
                new_description=plans[HUMAN_REVIEW].description
                + " Include the exact word VERIFIED in the work product.",
                new_name=None,
                new_estimated_duration=None,
                new_estimated_cost=None,
                additional_instructions=None,
            ),
            context,
            self.model,
        )
        await assign(
            state,
            AssignTaskAction(
                reasoning="Prove pending reassignment uses native Task replacement",
                task_id=str(plans[REMOVED].id),
                agent_id=human,
            ),
            context,
            self.model,
        )
        await remove_work(
            state,
            RemoveTaskAction(reasoning="Prove cancellation persists", task_id=plans[REMOVED].id),
            context,
        )
        await save_message(
            state,
            context,
            MANAGER_ACTOR_ID,
            human,
            "Keep the two work products distinct and concise.",
            "contract-manager-message",
        )
        for chunk in await decompose_work(
            state,
            DecomposeTaskAction(
                reasoning="Prove model decomposition", task_id=plans[DECOMPOSED].id
            ),
            context,
            self.model,
        ):
            yield chunk
        failed_plan = PlannedTask(
            id=uuid5(state.workflow.id, "contract/model-failure"),
            name="Expected model failure",
            description="A bounded policy failure remains a native failed task.",
        )
        blocked_plan = PlannedTask(
            id=uuid5(state.workflow.id, "contract/blocked-by-model-failure"),
            name="Blocked by failed work",
            description="Must not execute after its prerequisite fails.",
            dependency_task_ids=[failed_plan.id],
        )
        failed = await context.spawn_task(
            Task(
                task_slug="mag-contract-model-failure",
                instance_key="default",
                description=failed_plan.description,
                worker=ContractModelFailure(name="Expected failure", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=600),
            )
        )
        failed_result = await failed.wait(timeout_seconds=120)
        blocked = await context.spawn_task(
            Task(
                task_slug="mag-contract-blocked",
                instance_key="default",
                description=blocked_plan.description,
                worker=ContractGate(name="Must not run", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=600),
            ),
            depends_on=[failed.task_id],
        )
        for planned, handle in ((failed_plan, failed), (blocked_plan, blocked)):
            state.workflow.tasks[planned.id] = planned
            state.bindings[planned.id] = handle.task_id
        state.native_dependencies[blocked_plan.id] = [failed.task_id]
        await drain_admitted_work(state, context)

        async def observe() -> EpisodeState:
            return await project_native_state(state, context)

        state = await context.run_step("contract-final", observe, output_type=EpisodeState)
        completions = {
            name: await context.wait_for_task(state.bindings[plans[name].id], timeout_seconds=0)
            for name in assignees
        }
        chain = [completions[name] for name in CHAIN]
        if any(c.status != "completed" or c.output is None for c in chain):
            raise RuntimeError("A required contract role failed")
        review = completions[HUMAN_REVIEW]
        first = cast(WorkerOutput, review.output).metadata
        second = cast(WorkerOutput, completions[HUMAN_FOLLOW_UP].output).metadata
        checks = {
            "native_roles_completed": all(c.status == "completed" for c in chain),
            "dependency_order": all(
                cast(datetime, before.completed_at) <= cast(datetime, after.started_at)
                for before, after in zip(chain, chain[1:], strict=False)
            ),
            "fatigue_ledger": second["prior_hours"] == first["accounted_hours"]
            and second["fatigue"] > 0
            and str(review.execution_id) in second["prior_attempt_ids"],
            "pending_refinement": "VERIFIED" in cast(WorkerOutput, review.output).output,
            "cancellation": completions[REMOVED].status == "cancelled",
            "bounded_model_failure": failed_result.status == "failed"
            and failed_result.output is not None
            and not failed_result.output.success
            and state.workflow.tasks[failed_plan.id].status == TaskStatus.FAILED
            and not state.infrastructure_errors,
            "failed_prerequisite_does_not_execute": (await blocked.wait(timeout_seconds=0)).status
            == "cancelled",
            "decomposition": len(state.workflow.tasks[plans[DECOMPOSED].id].subtasks) >= 3,
            "manager_message": any(
                m.sender_id == MANAGER_ACTOR_ID and m.receiver_id == human
                for m in state.workflow.messages
            ),
            "role_message": any(
                m.sender_id in {ai, human, stakeholder} and m.receiver_id == MANAGER_ACTOR_ID
                for m in state.workflow.messages
            ),
        }
        receipt = {
            "checks": checks,
            "snapshot_hash": snapshot_hash(state),
            "snapshot": state.model_dump(mode="json"),
            "completions": [c.model_dump(mode="json") for c in completions.values()],
        }

        async def retain_receipt() -> RootModel[dict]:
            return RootModel[dict](receipt)

        frozen = await context.run_step(
            "contract-receipt", retain_receipt, output_type=RootModel[dict]
        )
        encoded = frozen.model_dump_json()
        await task.sandbox.write_file(CONTRACT_FILE, encoded.encode())
        yield WorkerOutput(output=encoded, metadata={"scripted_contract": True})


class MAGContractCriterion(Criterion):
    """Passes when every contract check held and the stored receipt matches the output."""

    type_slug: ClassVar[str] = "mag-native-contract"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        receipt = json.loads(context.worker_result.output)
        artifact = await context.task.sandbox.read_file(CONTRACT_FILE)
        checks = receipt["checks"]
        checks["artifact_matches_output"] = json.loads(artifact) == receipt
        checks["frozen_snapshot_digest"] = (
            snapshot_hash(EpisodeState.model_validate(receipt["snapshot"]))
            == receipt["snapshot_hash"]
        )
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=float(all(checks.values())),
            passed=all(checks.values()),
            feedback=json.dumps(checks),
            metadata={"checks": checks},
        )
