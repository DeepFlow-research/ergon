"""Scripted live composition contract; deliberately not an autonomous MAG score."""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
import json
from typing import ClassVar, cast
from uuid import uuid5

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.worker import WorkerOutput
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_builtins.benchmarks.manager_gym.actions import (
    AssignTaskAction,
    RefineTaskAction,
    RemoveTaskAction,
    DecomposeTaskAction,
)
from ergon_builtins.benchmarks.manager_gym.manager import (
    assign,
    refine_work,
    remove_work,
    decompose_work,
    save_message,
    drain_admitted_work,
)
from ergon_builtins.benchmarks.manager_gym.source_types import Task as PlannedTask
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    new_episode,
    apply_timeline,
    project_native_state,
    snapshot_hash,
)

CONTRACT_FILE = "/workspace/final_output/mag-contract.json"


class ContractGate(Worker):
    type_slug: ClassVar[str] = "mag-contract-gate"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        # Hold admission while the root proves pending mutations. Ergon owns the wait.
        await context.steps.sleep("pending-mutation-window", timedelta(seconds=30))
        yield WorkerOutput(output="gate released")


class CancellationContractWorker(Worker):
    type_slug: ClassVar[str] = "mag-cancellation-contract"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
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
        yield WorkerOutput(output="Cancellation did not stop the manager")


def contract_state() -> EpisodeState:
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery", seed=7))
    apply_timeline(state)
    tasks = []
    for index, name in enumerate(
        [
            "AI note",
            "Human review",
            "Human follow-up",
            "Stakeholder approval",
            "Remove me",
            "Decompose me",
        ]
    ):
        tasks.append(
            PlannedTask(
                id=uuid5(state.workflow.id, f"contract/{index}"),
                name=name,
                description="Write a brief one-sentence work product for a simulated project status update. Use the communication send_message tool to tell manager_agent what you produced.",
                estimated_duration_hours=1 if index == 1 else None,
            )
        )
    tasks[1].dependency_task_ids = [tasks[0].id]
    tasks[2].dependency_task_ids = [tasks[1].id]
    tasks[3].dependency_task_ids = [tasks[2].id]
    state.workflow.tasks = {t.id: t for t in tasks}
    state.workflow.resources = {}
    for actor in state.actors.values():
        if actor["agent_type"] == "human_mock":
            # Disable this branch only in the contract so two fatigue ledger entries are guaranteed.
            actor["misunderstanding_rate"] = 0
    return state


class MAGContractWorker(Worker):
    type_slug: ClassVar[str] = "mag-native-contract"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        async def initialize() -> EpisodeState:
            return contract_state()

        state = await context.run_step("contract-initialize", initialize, output_type=EpisodeState)
        names = [
            "AI note",
            "Human review",
            "Human follow-up",
            "Stakeholder approval",
            "Remove me",
            "Decompose me",
        ]
        plans = [next(t for t in state.workflow.tasks.values() if t.name == name) for name in names]
        ai = next(k for k in state.active_actors if state.actors[k]["agent_type"] == "ai")
        human = next(
            k for k in state.active_actors if state.actors[k]["agent_type"] == "human_mock"
        )
        stakeholder = next(
            k for k in state.active_actors if state.actors[k]["agent_type"] == "stakeholder"
        )
        gate = await context.spawn_task(
            Task(
                task_slug="mag-contract-gate",
                instance_key="default",
                description="Hold pending work for edit/cancel proof",
                worker=ContractGate(name="Contract gate", model="test:none"),
                sandbox=E2BSandbox(timeout_seconds=600),
            )
        )
        state.native_dependencies[str(plans[0].id)] = [gate.task_id]
        state.native_dependencies[str(plans[4].id)] = [gate.task_id]
        for planned, actor in zip(plans[:5], [ai, human, human, stakeholder, ai], strict=True):
            await assign(
                state,
                AssignTaskAction(
                    reasoning="Scripted native contract", task_id=str(planned.id), agent_id=actor
                ),
                context,
                self.model,
            )
        await refine_work(
            state,
            RefineTaskAction(
                reasoning="Prove pending Task payload replacement",
                task_id=plans[1].id,
                new_description=plans[1].description
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
                task_id=str(plans[4].id),
                agent_id=human,
            ),
            context,
            self.model,
        )
        await remove_work(
            state,
            RemoveTaskAction(reasoning="Prove cancellation persists", task_id=plans[4].id),
            context,
            self.model,
        )
        await save_message(
            state,
            context,
            "manager_agent",
            human,
            "Keep the two work products distinct and concise.",
            "contract-manager-message",
        )
        for chunk in await decompose_work(
            state,
            DecomposeTaskAction(reasoning="Prove model decomposition", task_id=plans[5].id),
            context,
            self.model,
        ):
            yield chunk
        await drain_admitted_work(state, context)

        async def observe() -> EpisodeState:
            return await project_native_state(state, context)

        state = await context.run_step("contract-final", observe, output_type=EpisodeState)
        completions = [
            await context.wait_for_task(state.bindings[str(p.id)], timeout_seconds=0)
            for p in plans[:5]
        ]
        if any(c.status != "completed" or c.output is None for c in completions[:4]):
            raise RuntimeError("A required contract role failed")
        first = cast(WorkerOutput, completions[1].output).metadata
        second = cast(WorkerOutput, completions[2].output).metadata
        checks = {
            "native_roles_completed": all(c.status == "completed" for c in completions[:4]),
            "dependency_order": all(
                cast(datetime, completions[i].completed_at)
                <= cast(datetime, completions[i + 1].started_at)
                for i in range(3)
            ),
            "fatigue_ledger": second["prior_hours"] == first["accounted_hours"]
            and second["fatigue"] > 0
            and str(completions[1].execution_id) in second["prior_attempt_ids"],
            "pending_refinement": "VERIFIED" in cast(WorkerOutput, completions[1].output).output,
            "cancellation": completions[4].status == "cancelled",
            "decomposition": len(state.workflow.tasks[plans[5].id].subtasks) >= 3,
            "manager_message": any(
                m.sender_id == "manager_agent" and m.receiver_id == human
                for m in state.workflow.messages
            ),
            "role_message": any(
                m.sender_id in {ai, human, stakeholder} and m.receiver_id == "manager_agent"
                for m in state.workflow.messages
            ),
        }
        receipt = {
            "checks": checks,
            "snapshot_hash": snapshot_hash(state),
            "snapshot": state.model_dump(mode="json"),
            "completions": [c.model_dump(mode="json") for c in completions],
        }
        encoded = json.dumps(receipt)
        await task.sandbox.write_file(CONTRACT_FILE, encoded.encode())
        yield WorkerOutput(output=encoded, metadata={"scripted_contract": True})


class MAGContractCriterion(Criterion):
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
