# Lossless Trace Events Plan

This document supersedes the earlier `Action` discriminated-union proposal.

The stronger proposal is:

- delete the `actions` table entirely
- introduce a canonical append-only `trace_events` table
- treat `trace_events` as the source of truth for all agent/runtime traces
- derive any dashboard-friendly or analytics-friendly summaries from `trace_events`

The motivation is broader than dashboard correctness.

The long-term goal is to store a lossless, replayable, training-grade record of:

- model observations
- model generations
- tool call arguments
- tool results
- streamed deltas where available
- ordering and timing

This makes the runtime usable not just for observability, but for future asynchronous RL and local model post-training.

## Core Thesis

The current `actions` table is not just lossy. It is conceptually the wrong layer.

It is:

- too tool-call-centric
- too UI-oriented
- too high-level for replay
- too low-fidelity for training

Even a discriminated-union `Action` schema would still be a compromise between:

- what the runtime actually emits
- what the dashboard wants to show

If the real target is an MDP-like, lossless runtime log, then the source of truth should be an append-only event log, not a summarized `Action` row.

## What Lossless Should Mean

For this system, "lossless" should mean:

- exact model request content sent to the provider
- exact model response content returned by the provider
- exact streamed deltas when the provider exposes them
- exact tool schemas available at decision time
- exact tool call arguments emitted by the model
- exact tool return payloads delivered back to the model
- exact observation payloads that the policy can see
- exact timestamps and ordering
- exact provider/model/settings metadata
- exact references to files or binary artifacts that were part of the context

This does not require storing provider token IDs immediately.

The important target is:

- text-exact
- byte-exact
- event-order-exact

## Proposed Direction

Delete `actions` as a persisted table and replace it with a new canonical event log table:

- `trace_events`

Everything that currently relies on `actions` should move to one of two things:

- direct reads from `trace_events` for training/export/replay systems
- derived projections for dashboard and UI consumption

## Source Of Truth vs Projection

The architecture should clearly separate:

### Canonical source of truth

- `trace_events`

### Derived projections

Examples:

- dashboard task trace stream
- dashboard tool-action summary rows
- run-level summaries
- tool usage analytics
- training trajectory exports

This is the key architectural shift.

The dashboard should not define the persistence model anymore.

## Proposed Canonical Table: `trace_events`

Introduce a new append-only table in `h_arcane/core/_internal/db/models.py`.

Recommended common columns:

- `id`
- `run_id`
- `task_id`
- `task_execution_id`
- `agent_id`
- `sequence_num`
- `event_kind`
- `event_payload_json`
- `created_at`
- `span_id`
- `parent_span_id`
- `provider_name`
- `model_name`
- `request_id`
- `agent_total_tokens`
- `agent_total_cost_usd`

Not every event kind needs every field populated.

The point is to preserve a stable envelope around typed event payloads.

## Proposed `event_kind`

This table should operate at the atomic runtime-event level.

Recommended initial kinds:

- `model_request`
- `model_response_part`
- `model_text_delta`
- `model_thinking_delta`
- `tool_call_requested`
- `tool_call_completed`
- `tool_call_failed`
- `observation_published`
- `resource_published`
- `reward_recorded`

You do not need every one of these on day one, but the schema should be designed for this level of fidelity.

## Proposed Payload Direction

Use `event_kind` as the discriminator and store the exact structured payload in `event_payload_json`.

Suggested event payload families:

### `ModelRequestTraceEvent`

Represents one full model request.

Suggested fields:

- `event_kind: Literal["model_request"]`
- `system_prompt: str | None`
- `instructions: str | None`
- `user_prompt: str | None`
- `message_history: list[dict]`
- `tool_schemas: list[dict]`
- `model_settings: dict | None`
- `provider_request_metadata: dict | None`

### `ModelResponsePartTraceEvent`

Represents one final assembled response part.

Suggested fields:

- `event_kind: Literal["model_response_part"]`
- `part_kind: str`
- `content: dict`
- `provider_response_metadata: dict | None`

This can store assembled `TextPart`, `ThinkingPart`, and similar parts.

### `ModelTextDeltaTraceEvent`

Represents one streamed text delta.

Suggested fields:

- `event_kind: Literal["model_text_delta"]`
- `delta: str`
- `part_index: int | None`

### `ModelThinkingDeltaTraceEvent`

Represents one streamed thinking delta.

Suggested fields:

- `event_kind: Literal["model_thinking_delta"]`
- `delta: str`
- `part_index: int | None`

### `ToolCallRequestedTraceEvent`

Represents one tool call emitted by the model.

Suggested fields:

- `event_kind: Literal["tool_call_requested"]`
- `tool_name: str`
- `tool_call_id: str`
- `args_json: dict | str | None`

### `ToolCallCompletedTraceEvent`

Represents the exact tool result returned into the agent loop.

Suggested fields:

- `event_kind: Literal["tool_call_completed"]`
- `tool_name: str`
- `tool_call_id: str`
- `result_json: dict | list | None`
- `result_text: str | None`
- `result_metadata: dict | None`

### `ToolCallFailedTraceEvent`

Represents a failed tool execution.

Suggested fields:

- `event_kind: Literal["tool_call_failed"]`
- `tool_name: str`
- `tool_call_id: str`
- `error: ExecutionError`

### `ObservationPublishedTraceEvent`

This is the RL-relevant layer.

Represents content that becomes observable to the policy after a tool call or environment change.

Suggested fields:

- `event_kind: Literal["observation_published"]`
- `source_kind: str`
- `observation_text: str | None`
- `observation_json: dict | list | None`
- `resource_ids: list[str]`

This event kind makes the future MDP extraction cleaner than simply treating tool outputs as synonymous with observations.

## Why Delete `actions`

Deleting `actions` is reasonable because once `trace_events` exists:

- `actions` no longer serves as the best canonical trace store
- `actions` becomes an unnecessary denormalized summary table
- trying to maintain both from the start increases ambiguity

If the dashboard still needs an "action stream", it should be derived from `trace_events`, either:

- on demand in API code
- via a materialized view or projection table later

That keeps the data model honest.

## Backend-Wide Changes

This change affects more than just one model file.

### 1. Database models

Primary file:

- `h_arcane/core/_internal/db/models.py`

Changes:

- add `TraceEventKind`
- add payload models for each initial event kind
- add discriminated union parser helpers
- add `TraceEvent` SQLModel
- delete `Action` SQLModel

Also update any indexes so the common access patterns remain efficient:

- by `run_id`, `sequence_num`
- by `task_id`, `sequence_num`
- by `task_execution_id`
- by `agent_id`
- by `event_kind`

### 2. Query layer

Primary file:

- `h_arcane/core/_internal/db/queries.py`

Changes:

- remove `ActionsQueries`
- add `TraceEventsQueries`
- add helpers like:
  - `get_all_for_run(run_id)`
  - `get_all_for_task(run_id, task_id)`
  - `get_by_execution(task_execution_id)`
  - `get_range(...)`

Ordering should be `sequence_num`, not ad hoc timestamps.

### 3. Worker execution runtime

Primary files:

- `h_arcane/benchmarks/common/workers/react_worker.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

Changes:

- stop constructing `Action` rows
- emit `TraceEvent` rows instead
- preserve ordered, append-only sequence numbers
- distinguish:
  - model request
  - text part
  - thinking part
  - tool call request
  - tool result
  - tool failure

This is the most important backend change after the schema itself.

### 4. Worker result contract

Primary file:

- `h_arcane/core/worker.py`

Current `WorkerResult` includes:

- `actions: list[Action]`

This should change.

Recommended replacement:

- `trace_events: list[TraceEvent]`

Or, more likely:

- remove trace rows from `WorkerResult` entirely
- emit trace events directly during runtime execution

The second option may be cleaner if you want a true append-only event log rather than a batched "return all trace rows at end" pattern.

### 5. Task execution persistence

Primary file:

- `h_arcane/core/_internal/task/persistence.py`

Changes:

- remove `queries.actions.create(...)` write path
- replace with `queries.trace_events.create(...)`
- ensure persistence works for append-only event flow

### 6. Dashboard event emitters

Primary files:

- `h_arcane/core/dashboard/events.py`
- `h_arcane/core/dashboard/emitter.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

Current events are based on agent actions:

- `dashboard/agent.action_started`
- `dashboard/agent.action_completed`

Those should no longer mirror a deleted table.

Recommended replacement:

- `dashboard/agent.trace_event_recorded`

Payload:

- `run_id`
- `task_id`
- `task_execution_id`
- `trace_event_id`
- `worker_id`
- `worker_name`
- `sequence_num`
- `event_kind`
- `payload`
- `created_at`

This gives the frontend a direct representation of the canonical event stream.

### 7. Run snapshot API

Primary file:

- `h_arcane/core/_internal/api/runs.py`

This file currently serializes `actionsByTask`.

That needs to change to a trace-oriented snapshot.

Recommended new shape:

- `traceByTask`

Each item should be a serialized trace-event state, not an action state.

The API can still derive a higher-level "tool action summary" if you want a compact view, but it should not be the only trace representation.

### 8. Any action-oriented internal assumptions

Search hits show action assumptions in:

- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/api/runs.py`
- any tests or deterministic harnesses that fabricate `Action`

All of these need to be updated to think in terms of trace events rather than action rows.

## Frontend-Wide Changes

This is also a larger frontend shift than just changing one panel.

### 1. Dashboard types

Primary file:

- `arcane-dashboard/src/lib/types.ts`

Current shape:

- `ActionState`
- `actionsByTask`
- action started/completed dashboard event types

Recommended change:

- replace `ActionState` with `TraceEventState`
- replace `actionsByTask` with `traceByTask`
- replace action event payload types with trace-event payload types

Suggested top-level TS shape:

```ts
export type TraceEventKind =
  | "model_request"
  | "model_response_part"
  | "model_text_delta"
  | "model_thinking_delta"
  | "tool_call_requested"
  | "tool_call_completed"
  | "tool_call_failed"
  | "observation_published"
  | "resource_published"
  | "reward_recorded";

export interface TraceEventState {
  id: string;
  taskId: string;
  taskExecutionId: string | null;
  workerId: string;
  workerName: string;
  sequenceNum: number;
  eventKind: TraceEventKind;
  payload: Record<string, unknown>;
  createdAt: string;
}
```

You can refine payload typing later, but the FE store should stop pretending everything is a tool action.

### 2. Dashboard store

Primary files:

- `arcane-dashboard/src/lib/state/store.ts`
- `arcane-dashboard/src/hooks/useRunState.ts`
- `arcane-dashboard/src/hooks/useTaskDetails.ts`
- `arcane-dashboard/src/lib/testing/dashboardHarness.ts`
- `arcane-dashboard/src/lib/socket/server.ts`

Changes:

- replace `actionsByTask` with `traceByTask`
- append trace events in sequence order
- stop merging by started/completed action lifecycle
- support append-only event ingestion

This becomes simpler if trace events are only ever appended.

### 3. Inngest dashboard event handlers

Primary file:

- `arcane-dashboard/src/inngest/functions/index.ts`

Changes:

- remove the action started/completed handlers
- add a trace-event-recorded handler
- update the store write path

### 4. Action stream panel becomes trace panel

Primary file:

- `arcane-dashboard/src/components/panels/ActionStreamPanel.tsx`

This component is currently highly action-specific.

It should be replaced or renamed to something like:

- `TraceStreamPanel`

It should render event kinds differently:

- `model_request`
  - collapsible prompt/messages/tool-schema block

- `model_response_part`
  - text or thinking content

- `model_text_delta`
  - likely hidden or grouped unless a live token view is enabled

- `model_thinking_delta`
  - likely hidden or grouped unless a live reasoning view is enabled

- `tool_call_requested`
  - tool name + args

- `tool_call_completed`
  - tool name + result

- `tool_call_failed`
  - tool name + error

- `observation_published`
  - what became visible to the agent

The current input/output block UI is too narrow for this new model.

### 5. Task workspace and run workspace

Primary files:

- `arcane-dashboard/src/components/workspace/TaskWorkspace.tsx`
- `arcane-dashboard/src/components/run/RunWorkspacePage.tsx`

Changes:

- rename "Actions" to "Trace" or "Agent Trace"
- update action counts to trace-event counts
- decide whether to show:
  - raw trace
  - grouped trace
  - only selected event kinds by default

This matters because a lossless event log will be more verbose than the old action stream.

### 6. Fixtures and tests

Primary areas:

- `arcane-dashboard/tests/helpers/dashboardFixtures.ts`
- any action-panel tests
- run-state fixtures

Changes:

- replace action fixtures with trace-event fixtures
- add representative cases for:
  - model request
  - thinking response
  - text response
  - tool request
  - tool completion
  - observation publication

## Recommendation On FE Presentation

The canonical backend log should be lossless.

The frontend should probably not show every raw event by default in a naive chronological list.

Recommended UI split:

### Raw trace view

Use for debugging and research:

- exact event stream
- ordered
- verbose

### Task narrative / grouped trace view

Use for normal workflow inspection:

- grouped model turn
- grouped tool invocation
- grouped observation blocks

This grouped view should be derived client-side or API-side from `trace_events`, not stored as a separate source of truth.

## Training / RL Implications

This schema change is justified by the long-term goal of turning Arcane into an asynchronous RL framework.

For that future, the important thing is that `trace_events` makes it possible to reconstruct:

- what the model observed
- what the model generated
- what the environment returned
- what changed in the world after an action

That means a later training extractor can derive:

- observation
- action
- next observation
- reward
- done

without requiring the original runtime to be redesigned again.

This is much harder if the source of truth remains a lossy dashboard-oriented action log.

## Migration Strategy

This is a larger migration than the earlier action-union proposal, so it should be phased carefully.

### Phase 1: Introduce `trace_events`

Backend:

- add `TraceEvent` model
- add `TraceEventsQueries`
- start emitting `trace_events`

Do not delete `actions` in the same commit if you want a safer rollout.

### Phase 2: Switch runtime writes to `trace_events`

Backend:

- `ReActWorker` and worker execution stop emitting `Action`
- runtime writes only `trace_events`

At this point, `actions` can be treated as dead or transitional.

### Phase 3: Change dashboard APIs and events

Backend:

- update run snapshot API
- replace action events with trace-event events

Frontend:

- update types and store

### Phase 4: Replace action UI with trace UI

Frontend:

- replace `ActionStreamPanel`
- update task workspace and run workspace references
- update fixtures/tests

### Phase 5: Delete `actions`

Backend:

- remove `Action` model
- remove action queries
- remove any remaining action-specific references

Frontend:

- remove all remaining action assumptions

## Recommended Implementation Order

1. Update `h_arcane/core/_internal/db/models.py`
2. Update `h_arcane/core/_internal/db/queries.py`
3. Update `h_arcane/core/worker.py` result contract if needed
4. Update `h_arcane/benchmarks/common/workers/react_worker.py`
5. Update `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
6. Update `h_arcane/core/_internal/api/runs.py`
7. Update `h_arcane/core/dashboard/events.py`
8. Update `h_arcane/core/dashboard/emitter.py`
9. Update `arcane-dashboard/src/lib/types.ts`
10. Update `arcane-dashboard/src/lib/state/store.ts`
11. Update `arcane-dashboard/src/hooks/useRunState.ts`
12. Update `arcane-dashboard/src/hooks/useTaskDetails.ts`
13. Update `arcane-dashboard/src/inngest/functions/index.ts`
14. Replace `ActionStreamPanel` with a trace-oriented panel
15. Update `TaskWorkspace.tsx` and `RunWorkspacePage.tsx`
16. Update fixtures and tests
17. Delete `Action` and all remaining action-specific code paths

## Risks

### 1. Event volume

A lossless event log will be much larger than the current action stream.

You will need to think about:

- indexing
- pagination
- retention
- FE rendering strategy

### 2. UI verbosity

The current dashboard expects a compact tool-action stream.

A raw trace stream is noisier, so some grouping/filtering strategy will likely be needed.

### 3. Runtime coupling

If some code keeps thinking in terms of actions and some in terms of trace events, the migration will get messy.

The conceptual shift needs to be made cleanly.

### 4. Training assumptions

Lossless event capture is necessary for future RL/post-training, but not sufficient by itself.

You will still need later work for:

- reward modeling
- trajectory extraction
- observation boundary definition
- policy/environment semantics

Still, this schema change is the right foundational move.

## Recommendation

The recommended path now is:

- stop evolving `actions`
- introduce `trace_events` as the canonical event log
- delete `actions` once the dashboard and API migrate
- let the frontend consume trace events or grouped trace projections
- preserve the raw runtime stream as the training-grade source of truth

This better matches both:

- the PydanticAI runtime shape
- the longer-term goal of turning Arcane into a replayable asynchronous RL framework
