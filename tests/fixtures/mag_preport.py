"""Deterministic native lifecycle canary, not a MAG implementation."""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.api.worker import WorkerOutput

FILE = "/workspace/final_output/native-proof.txt"


class PreportWorker(Worker):
    type_slug: ClassVar[str] = "mag-preport-proof"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        await task.sandbox.write_file(FILE, b"native-proof")
        yield WorkerOutput(
            output="native-proof",
            success=True,
            metadata={"actor_key": "alice", "simulated_hours": 1},
        )


class PreportCriterion(Criterion):
    type_slug: ClassVar[str] = "mag-preport-proof"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        data = await context.task.sandbox.read_file(FILE)
        passed = (
            data in (b"native-proof", "native-proof")
            and context.worker_result.output == "native-proof"
        )
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=float(passed),
            passed=passed,
            weight=1,
            feedback=f"sandbox read type={type(data).__name__}; worker output and artifact checked",
        )


class ContinuationWorker(Worker):
    """Live real-model checkpoint -> two native spawns -> durable completion reads."""

    type_slug: ClassVar[str] = "mag-continuation-proof"

    async def execute(self, task: Task, *, context: WorkerContext):
        async def decide():
            return await infer(
                model=self.model,
                system="Follow the exact requested proof contract.",
                prompt="Return text native-proof and child_count 2.",
                output_type=ContinuationDecision,
            )

        decision = await context.run_step("proof-policy", decide, output_type=InferenceResult)
        for chunk in decision.chunks:
            yield chunk
        parsed = ContinuationDecision.model_validate(decision.output)
        if parsed.child_count != 2 or parsed.text != "native-proof":
            raise ValueError("Model did not satisfy continuation proof contract")
        children = []
        for index in range(parsed.child_count):
            child = await context.spawn_task(
                Task(
                    task_slug=f"proof-child-{index}",
                    instance_key="proof",
                    description="Produce a durable artifact for the continuation proof.",
                    worker=PreportWorker(
                        name=f"child-{index}", actor_key=f"person-{index}", model="test:none"
                    ),
                    sandbox=E2BSandbox(timeout_seconds=600),
                ),
                depends_on=tuple(c.task_id for c in children),
            )
            children.append(child)
        completed = [await child.wait(timeout_seconds=180) for child in children]
        if any(
            c.status != "completed" or c.output is None or c.output.output != "native-proof"
            for c in completed
        ):
            raise ValueError(f"Child failed or timed out: {completed}")
        await task.sandbox.write_file(FILE, b"native-proof")
        yield WorkerOutput(
            output=parsed.text,
            metadata={
                "children": [c.model_dump(mode="json") for c in completed],
                "model_input_tokens": decision.input_tokens,
                "model_output_tokens": decision.output_tokens,
            },
        )


from pydantic import BaseModel
from ergon_builtins.benchmarks.manager_gym.inference import infer, InferenceResult
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


class ContinuationDecision(BaseModel):
    text: str
    child_count: int
