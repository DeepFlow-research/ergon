# Final Worker Output Source of Truth

_Sketch for treating `WorkerOutput` as the semantic final answer, rather than inferring it from context transcript events._

---

## Problem

`ReActWorker.get_output()` currently reconstructs the worker's final output by reading persisted `RunContextEvent` rows and taking the last `assistant_text`, with a fallback that searches for a `final_result` tool call. That works, but it conflates three different concepts:

- `assistant_text`: model text emitted during a generation turn
- `tool_call(final_result)`: PydanticAI's structured-output protocol
- `WorkerOutput`: the worker's final semantic result for the task execution

The final answer should not be inferred from transcript shape. It should be the explicit output returned by the worker and persisted by the runtime.

## Current State

The codebase already has most of the right destination:

- `WorkerOutput(output=..., success=..., metadata=...)` is the worker API's semantic final result.
- `worker_execute_fn()` receives the worker's `WorkerOutput` after `worker.get_output(worker_context)`.
- `WorkerExecuteResult.final_assistant_message` carries that value from `worker-execute` back to `task-execute`.
- `execute_task_fn()` passes `worker_result.final_assistant_message` into `FinalizeTaskExecutionCommand`.
- `TaskExecutionService.finalize_success()` persists it to `RunTaskExecution.final_assistant_message`.
- `RunTaskExecution` also has `output_json` for structured execution output metadata.

So the persistence model already has a first-class execution-level field for the final assistant message. The weak part is upstream: `ReActWorker.get_output()` still computes that value by re-reading the context-event transcript.

## Desired Shape

The runtime should treat final worker output as execution-level data, not as another transcript event.

```text
worker.execute() yields GenerationTurn events
        |
        v
ContextEventRepository persists transcript evidence
        |
        v
worker.get_output() returns WorkerOutput
        |
        v
TaskExecutionService.finalize_success() persists execution result
        |
        v
RunTaskExecution.final_assistant_message / output_json are the source of truth
```

In this model:

- `RunContextEvent` remains the append-only transcript log.
- `RunTaskExecution.final_assistant_message` is the final human-readable answer.
- `RunTaskExecution.output_json` can hold structured metadata from `WorkerOutput.metadata`.
- Rollout-card export reads both: context events for the trace, task execution fields for final execution outputs.

## Proposed Contract

`WorkerOutput` should be the only object that defines a worker's final semantic output.

```python
class WorkerOutput(BaseModel):
    output: str
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
```

The runtime should persist it as:

```text
RunTaskExecution.final_assistant_message = WorkerOutput.output
RunTaskExecution.output_json = {
    "worker_output": {
        "success": WorkerOutput.success,
        "metadata": WorkerOutput.metadata,
    },
    "resource_ids": [...]
}
```

If we want the full `WorkerOutput` object available in exports, use `output_json["worker_output"]` rather than adding a new `RunContextEvent` type.

## ReActWorker Implication

`ReActWorker` should stop deriving output by querying `ContextEventRepository`.

Instead, it should capture the structured final result while running the PydanticAI agent. The worker already configures:

```python
agent: Agent[None, _AgentOutput] = Agent(
    model=resolved.model,
    instructions=self.system_prompt or None,
    tools=self.tools,
    output_type=_AgentOutput,
)
```

The final `_AgentOutput.final_assistant_message` should be stored on the worker instance during `execute()`, then returned directly from `get_output()`.

Conceptually:

```python
class ReActWorker(Worker):
    def __init__(...):
        ...
        self._final_output: _AgentOutput | None = None
        self._turn_count = 0

    async def _run_agent(...):
        async with agent.iter(...) as run:
            ...
        self._final_output = run.result.output

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        if self._final_output is None:
            return WorkerOutput(output="", success=False)
        return WorkerOutput(
            output=self._final_output.final_assistant_message,
            success=True,
            metadata={
                "reasoning": self._final_output.reasoning,
                "turn_count": self._turn_count,
            },
        )
```

The exact PydanticAI result access may differ, but the ownership is the important part: the worker returns the structured final result it received from the agent, rather than reconstructing it from persisted context events.

## Why Not `final_agent_message` Context Events?

A new context event type would make the transcript easier to query, but it blurs the abstraction boundary.

`RunContextEvent` should answer: "What happened during the model/tool interaction?"

`RunTaskExecution` should answer: "What did this worker execution finally produce?"

The final output belongs to the second question. Mirroring it into a rollout-card export is useful; storing it as another transcript event is optional and should not be the source of truth.

## Implementation Sketch

1. Keep `ContextEventRepository` unchanged as the transcript serializer.
2. Update `WorkerExecuteResult` only if needed to carry `WorkerOutput.metadata`.
3. Update `FinalizeTaskExecutionCommand` to carry `worker_output_metadata` or a full `worker_output_json`.
4. Update `TaskExecutionService.finalize_success()` to persist:
   - `final_assistant_message`
   - `output_json["worker_output"]`
   - existing `resource_ids` if present
5. Update `ReActWorker` to capture its PydanticAI structured result during execution.
6. Replace `ReActWorker._base_output()` with a simple read of the captured structured output.
7. Remove `_latest_final_result_message()` if no other worker needs it.
8. Update rollout-card export to include task execution final outputs from `RunTaskExecution`, not by scanning `RunContextEvent`.

## Migration / Compatibility

Existing completed runs may only have context events, so readers should remain tolerant:

- Prefer `RunTaskExecution.final_assistant_message`.
- If absent, optionally fall back to the old transcript inference for legacy runs.
- Do not use the fallback in new execution paths.

This preserves old data while making new runs explicit.

## Tests

Add focused tests for:

- `ReActWorker.get_output()` returns the captured structured `_AgentOutput`, not the last `assistant_text`.
- A run with intermediate `assistant_text` plus final structured output persists the structured final output.
- `TaskExecutionService.finalize_success()` writes `final_assistant_message` and `output_json["worker_output"]`.
- Context event replay still reconstructs transcript messages without needing final-output semantics.
- Legacy read helpers fall back to transcript inference only when `RunTaskExecution.final_assistant_message` is missing.

## Open Questions

1. Should `WorkerExecuteResult` carry the full `WorkerOutput.metadata`, or should `worker_execute_fn()` persist it directly before returning?
2. Should `RunTaskExecution.output_json` store the full `WorkerOutput` shape, or only `metadata` plus resource references?
3. Should rollout-card export call this field `worker_output`, `execution_output`, or `final_worker_output`?
