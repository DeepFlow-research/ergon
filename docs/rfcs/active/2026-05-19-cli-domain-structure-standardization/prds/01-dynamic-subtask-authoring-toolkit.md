# PRD 01: Move Dynamic Subtask Authoring Out Of CLI

## Goal

Make dynamic subtask authoring a real object-bound runtime capability exposed to
agents through builtins toolkits, not through `ergon_cli` command handlers.

The end state is:

- `ergon_core.api.WorkerContext.spawn_task(Task(...))` remains the canonical
  authoring API.
- `ergon_builtins` owns agent-facing tools that wrap that API.
- `ergon_cli` no longer exposes or implements live dynamic task creation.
- A toy integration test proves an agent/tool can spawn a real dynamic child
  task under a benchmark sample.

## Problem

The current CLI command surface suggests that dynamic task authoring can happen
through:

```bash
ergon workflow ... manage add-task --task-slug ... --description ... --worker ...
```

That shape is now wrong for the v2 object-bound architecture. It only carries
strings and slugs, while the real runtime contract requires a full
`Task(...)` object with inline worker, sandbox, and evaluator configuration.

Core already enforces this direction:

- `WorkflowService.add_task(..., dry_run=False)` raises with the message:
  `add-task requires an object-bound Task in the final v2 schema; use WorkerContext.spawn_task(Task(...)) for dynamic tasks.`
- `TaskManagementService.add_subtask()` and `plan_subtasks()` reject the retired
  slug-based API.
- `WorkerContext.spawn_task(Task(...))` is the sanctioned path and writes the
  full task snapshot into `run_graph_nodes.task_json` with `is_dynamic=True`.

The current package split also creates an inverted dependency:

`ergon_builtins.tools.workflow_cli_tool` imports `ergon_cli.commands.workflow`
to expose a single agent-facing `workflow(command)` tool.

That means a builtins agent toolkit depends on the human/operator CLI package.
The ownership should be reversed conceptually: builtins can expose a CLI-like
agent tool, but the implementation must wrap core APIs directly or use a
builtins-owned parser, not import `ergon_cli`.

## Non-Goals

This PRD does not redesign every workflow inspection command.

It should not:

- remove useful workflow inspection from human CLI if it remains operator-facing
- rewrite the full workflow resource browser
- redesign all builtins toolkits
- create a generic string-command language in core
- allow workers to mutate arbitrary graph nodes outside their containment scope

## Architecture Decision

Dynamic subtask creation is an authoring/runtime API, not a CLI domain.

The layering should become:

```text
ergon_core.api
  WorkerContext.spawn_task(Task(...))
  WorkerContext.cancel_task(...)
  WorkerContext.refine_task(...)
  WorkerContext.restart_task(...)
  WorkerContext.get_task(...)

ergon_builtins.tools
  SubtaskLifecycleToolkit
    typed agent tools over WorkerContext

  WorkflowCliToolkit
    optional single string-command tool for agents
    implemented in builtins, wrapping core/builtins capabilities

ergon_cli
  human/operator commands only
  no live dynamic task authoring command
```

The agent-facing CLI-like tool is allowed to exist, but it is a toolkit
implementation detail in `ergon_builtins`, not the public CLI package's
responsibility.

## Proposed Changes

### 1. Delete workflow management from `ergon_cli`

Problem:

`ergon_cli.commands.workflow` exposes `manage add-task`, `add-edge`,
`restart-task`, and `abandon-task`. Only dry-run behavior is supported for most
actions, and live `add-task` delegates to a core service that intentionally
rejects slug-based creation.

Solution:

Delete the whole `workflow manage` branch from the human CLI. The command-shaped
workflow management grammar belongs to the builtins agent toolkit, where it can
wrap `WorkerContext` and construct object-bound tasks. `ergon_cli` may keep
workflow inspection only if it is useful for operator debugging, but it must not
own graph mutation or sandbox/task management commands.

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Delete `manage` parser branch | `ergon_cli/commands/workflow.py` | no human CLI workflow management surface |
| Delete `_handle_manage` and manage dispatch | `ergon_cli/commands/workflow.py` | builtins owns command-shaped management |
| Move/replace resource materialization if agent-facing | `ergon_cli/commands/workflow.py` | builtins workflow toolkit or typed builtins tool |
| Keep inspect commands if useful | `ergon_cli/commands/workflow.py` now; later `ergon_cli/domains/workflow/` | operator/debug surface only |

Acceptance:

- `ergon_cli` no longer registers `workflow manage`.
- `ergon_cli.commands.workflow` no longer implements `_handle_manage`.
- `ergon_cli` no longer imports workflow mutation services for graph management.
- CLI parser tests assert `ergon workflow manage ...` is not a valid human CLI
  command.
- Builtins integration tests assert `workflow("manage add-subtask ...")` still
  works for agents.

### 2. Move the single-command agent workflow tool into builtins ownership

Problem:

`ergon_builtins.tools.workflow_cli_tool` imports
`ergon_cli.commands.workflow.execute_workflow_command`. That makes a builtins
agent tool depend on the CLI package.

Solution:

Introduce a builtins-owned workflow command adapter. It may keep the
`workflow(command: str)` UX for agents, but its implementation should live under
`ergon_builtins.tools` and call core/public runtime facades directly.

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Stop importing `ergon_cli.commands.workflow` | `ergon_builtins/tools/workflow_cli_tool.py` | remove CLI dependency |
| Add builtins parser/dispatcher for agent command string | new `ergon_builtins/tools/workflow_command_adapter.py` | parses agent workflow commands |
| Keep factory name or provide compatibility wrapper | `ergon_builtins/tools/workflow_cli_tool.py` | delegates to builtins adapter |

Initial command scope:

```text
inspect resource-list
inspect resource-content
inspect task-tree
inspect task-dependencies
inspect next-actions
manage add-subtask
```

The `manage add-subtask` command must create an object-bound `Task`, not a
slug-only mutation.

Acceptance:

- `rg "ergon_cli" ergon_builtins/ergon_builtins/tools` returns no production
  imports.
- The agent-facing `workflow(command)` tool still injects run/task/execution
  identity from `WorkerContext`.
- The command adapter rejects context flags supplied by the model.

### 3. Add reusable toy object-bound fixtures for integration tests

Problem:

To prove dynamic subtask spawning works end-to-end, tests need a small
serializable task/worker/sandbox combination that is not tied to an external
benchmark service. The same fixture should also be reused for negative tests so
the builtins adapter proves it respects core's authoring laws instead of only
passing the happy path.

Solution:

Add reusable test fixtures that build a complete object-bound `Task`, a parent
run graph node, and a `WorkerContext` wired through the normal runtime facade.
Use those fixtures for both successful dynamic spawning and prohibited mutation
tests.

Proposed toy classes:

```python
class ToySandbox(Sandbox):
    type_slug: ClassVar[str] = "toy-sandbox"

    async def provision(self) -> None:
        return None


class ToyWorker(Worker):
    type_slug: ClassVar[str] = "toy-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=f"completed {task.task_slug}", success=True)
```

Proposed code and location:

| Test Asset | Location |
| --- | --- |
| Toy task, worker, sandbox, and graph fixtures | `ergon_builtins/tests/fixtures/toy_workflow.py` |
| Adapter tests | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` |
| Typed lifecycle toolkit tests | `ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py` |
| Core spawn assertions can reuse existing helpers | `ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py` |

Acceptance:

- The toy spawned task persists as a `RunGraphNode`.
- The node has `is_dynamic=True`.
- The node's `task_json` contains a serializable `_type` discriminator for the
  task, worker, and sandbox.
- No `ExperimentDefinitionTask` row is written for the dynamic child.
- The same fixture is reused by tests that assert prohibited authoring paths are
  blocked.
- The fixture does not require E2B, Docker, provider SDKs, or external benchmark
  assets.

Required fixture API:

```python
class ToyWorkflowHarness(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
    )

    run_id: UUID
    parent_task_id: UUID
    parent_task: Task
    context: WorkerContext

    def child_task(self, *, task_slug: str, description: str) -> Task: ...
    def nodes(self) -> list[RunGraphNode]: ...
    def edges(self) -> list[RunGraphEdge]: ...
    def definition_tasks(self) -> list[ExperimentDefinitionTask]: ...
```

The harness should hide session setup details from tests while still letting
assertions inspect graph rows directly.

### 3a. Reuse the toy fixture for authoring-law tests

Problem:

A happy-path spawn test can pass even if the builtins adapter accidentally
creates side doors for graph mutation. The integration suite should verify that
agent-facing tools cannot bypass core's runtime rules.

Solution:

Use the toy harness to assert the builtins workflow adapter delegates to
`WorkerContext` and `WorkflowGraphRepository` rather than performing its own
graph writes.

Required test cases:

| Test | Location | Expected Behavior |
| --- | --- | --- |
| Happy-path child spawn | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | `manage add-subtask` writes one `RunGraphNode` with `is_dynamic=True` and object-bound `task_json`. |
| No definition-row write | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | Spawning a child leaves `ExperimentDefinitionTask` count unchanged. |
| Context escape blocked | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | Agent-supplied `--run-id`, `--node-id`, `--execution-id`, or `--sandbox-task-key` is rejected before service calls. |
| Slug-only task creation blocked | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | Commands that try to specify only `--worker`/`--task-slug` without building a `Task` return a clear object-bound error. |
| Dependency edge is written through core | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | `manage add-subtask --depends-on <node-id>` creates a graph edge through `WorkerContext.spawn_task(..., depends_on=...)`. |
| Cycle-creating dependency is rejected | `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py` | A dependency request that would create a graph cycle raises/returns the core `CycleError` message and writes no new edge. |
| Non-descendant lifecycle mutation blocked | `ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py` | `cancel_task`, `refine_task`, `restart_task`, or `get_task` against a non-descendant returns `ContainmentViolation`. |
| Typed toolkit spawn uses same path | `ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py` | `SubtaskLifecycleToolkit.add_subtask(task)` writes the same dynamic graph shape as the CLI-like adapter. |

Acceptance:

- Negative tests assert row counts before and after the rejected call.
- Rejected calls do not leave partial `RunGraphNode` or `RunGraphEdge` rows.
- Tests compare failure messages to core errors where the core error is already
  part of the public/runtime contract.
- The builtins adapter has no direct SQLModel insert path for dynamic nodes or
  edges.

### 4. Implement real dynamic spawning in the builtins toolkit

Problem:

The current single-command workflow tool can only dry-run `add-task` through the
CLI path. That does not exercise the real object-bound dynamic authoring API.

Solution:

Add a builtins-owned command that maps an agent request to an object-bound
`Task`. For the first implementation, keep the supported live-spawn shape small
and explicit.

Recommended first command:

```text
manage add-subtask --task-slug <slug> --description <description> [--depends-on <node-id> ...]
```

The adapter should construct the child task by copying the current task's
runtime contract:

- `instance_key` from the current task
- `worker` from the current task, or a benchmark/toolkit-provided child worker
- `sandbox` from the current task, if the sandbox object is reusable
- `evaluators` from the current task, unless the benchmark toolkit provides a
  narrower evaluator set

If copying the current task's sandbox/worker/evaluators is not valid for a
benchmark, that benchmark should provide a task factory to the toolkit.

Proposed code and location:

| Responsibility | Location |
| --- | --- |
| Agent command parsing | `ergon_builtins/tools/workflow_command_adapter.py` |
| Object-bound child task construction | `ergon_builtins/tools/dynamic_task_factory.py` |
| Existing `workflow(command)` factory | `ergon_builtins/tools/workflow_cli_tool.py` |
| Typed lifecycle tools | `ergon_builtins/tools/subtask_lifecycle_toolkit.py` |

Proposed interface:

```python
class DynamicTaskFactory(Protocol):
    def child_task(
        self,
        *,
        parent: Task,
        task_slug: str,
        description: str,
    ) -> Task: ...
```

Default behavior:

```python
def default_child_task_factory(
    *,
    parent: Task,
    task_slug: str,
    description: str,
) -> Task:
    return parent.model_copy(
        update={
            "task_slug": task_slug,
            "description": description,
            "parent_task_slug": parent.task_slug,
        }
    )
```

Acceptance:

- The builtins workflow tool can spawn a real dynamic child task in an
  integration test.
- The child task is object-bound and round-trippable through `Task.from_definition`.
- Benchmarks can override child task construction without editing core.

### 5. Keep typed subtask lifecycle tools as the preferred agent API

Problem:

A single string-command tool is attractive for prompt simplicity, but typed
tools are safer and easier to validate.

Solution:

Treat `SubtaskLifecycleToolkit` as the preferred structured API. The CLI-like
`workflow(command)` tool is an alternate UX for agents that benefit from a
shell-style command vocabulary.

Proposed code and location:

| Action | Current Location | Target |
| --- | --- | --- |
| Ensure `add_subtask(task: Task, depends_on: list[str] | None)` remains object-bound | `ergon_builtins/tools/subtask_lifecycle_toolkit.py` | keep as preferred typed tool |
| Fix stale comments about missing containment if core now enforces it | `ergon_builtins/tools/subtask_lifecycle_toolkit.py` | docs match `WorkerContext` behavior |
| Add tests for typed toolkit spawning | `ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py` | proves typed path still works |

Acceptance:

- `SubtaskLifecycleToolkit.add_subtask` delegates to `WorkerContext.spawn_task`.
- Cancellation/refinement/restart/get operations go through `WorkerContext`.
- Comments do not claim service-layer containment gaps that are now handled by
  the facade.

## Integration Test Plan

### Test 1: builtins workflow command spawns a toy dynamic child

File:

`ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`

Scenario:

1. Create a test run and a parent `RunGraphNode` with an object-bound toy task
   snapshot.
2. Construct a `WorkerContext` for the parent node using the normal runtime
   service injection path.
3. Build `workflow(command)` from the builtins toolkit.
4. Call:

   ```python
   await workflow('manage add-subtask --task-slug child --description "child work"')
   ```

5. Query `RunGraphNode` rows.
6. Assert exactly one dynamic child exists.
7. Assert no `ExperimentDefinitionTask` row was inserted.
8. Assert `Task.from_definition(child.task_json)` reconstructs a task whose
   `task_slug == "child"`.

Expected result:

- The test passes without importing `ergon_cli`.
- The dynamic child is persisted through `WorkerContext.spawn_task`.

### Test 2: builtins workflow command rejects context escape flags

File:

`ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`

Scenario:

Call:

```python
await workflow('inspect task-tree --run-id 00000000-0000-0000-0000-000000000000')
```

Expected result:

- The tool returns an error explaining that context flags are injected by the
  runtime and cannot be supplied by the agent.
- No query or mutation is attempted for the supplied fake ID.

### Test 3: human CLI has no workflow management surface

File:

`ergon_cli/tests/unit/cli/test_workflow_cli.py`

Scenario:

Call the CLI parser or entrypoint with:

```text
workflow manage add-task --task-slug child --description "child work" --worker toy-worker
```

Expected result:

- The command is rejected by argparse because `manage` is not a registered
  human CLI workflow subcommand.
- No graph node is inserted.

### Test 4: builtins workflow command writes dependency edges through core

File:

`ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`

Scenario:

1. Use the toy harness to create a parent node and an existing sibling/child
   dependency source node.
2. Call:

   ```python
   await workflow(
       f'manage add-subtask --task-slug child --description "child work" '
       f'--depends-on {dependency_source_id}'
   )
   ```

3. Query `RunGraphEdge` rows.

Expected result:

- Exactly one edge is created from `dependency_source_id` to the spawned child.
- The edge is created by core graph APIs, not by adapter-local SQLModel writes.
- The spawned task is not dispatched immediately if it has unsatisfied
  dependencies.

### Test 5: builtins workflow command cannot create cyclic dependencies

File:

`ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`

Scenario:

1. Use the toy harness to create a graph where adding the requested dependency
   would create a cycle.
2. Call the workflow command that would request that dependency.

Expected result:

- The tool returns/raises the core `CycleError` message.
- `RunGraphEdge` count is unchanged.
- `RunGraphNode` count is unchanged unless the implementation validates the
  dependency before spawning; if the implementation creates the node first, that
  behavior is rejected and the test should fail.

### Test 6: typed subtask lifecycle toolkit enforces containment

File:

`ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py`

Scenario:

1. Use the toy harness to create two unrelated task subtrees in the same run.
2. Build `SubtaskLifecycleToolkit(context=parent_context)`.
3. Attempt `cancel_task`, `refine_task`, `restart_task`, and `get_subtask`
   against a node outside `parent_context`'s descendant tree.

Expected result:

- Each operation returns a failure containing `ContainmentViolation` or raises
  that exception before mutation.
- Node status, description, and graph rows remain unchanged.

## Proposed PR Shape

This PR should come after PRD 00's basic hygiene cleanup or include only the
minimal overlapping workflow flag cleanup needed to avoid conflicts.

Recommended order:

1. Add integration tests that demonstrate the desired builtins-owned dynamic
   spawning behavior and initially fail.
2. Add `ergon_builtins.tools.dynamic_task_factory`.
3. Add `ergon_builtins.tools.workflow_command_adapter`.
4. Update `ergon_builtins.tools.workflow_cli_tool` to use the builtins adapter
   instead of importing `ergon_cli`.
5. Delete `workflow manage` from `ergon_cli.commands.workflow`; keep any
   agent-facing management grammar only in builtins.
6. Update tests and docs references.

## Verification Commands

Run:

```bash
uv run ruff check ergon_cli/ergon_cli ergon_builtins/ergon_builtins
uv run pytest ergon_cli/tests/unit/cli/test_workflow_cli.py
uv run pytest ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py
uv run pytest ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py
uv run pytest ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py
```

## Open Decisions

### Should the CLI-like builtins tool support live `add-subtask`?

Recommended decision:

Yes, but only through object-bound task construction. It must never accept a
worker slug and synthesize an incomplete graph node.

### Should the builtins workflow command copy the parent task by default?

Recommended decision:

Yes for the first toy/integration path, because it proves the API without
inventing benchmark-specific factories too early. Benchmarks with special child
task requirements can provide a `DynamicTaskFactory`.

### Should human CLI keep workflow inspect commands?

Recommended decision:

Yes, if useful for debugging. Inspect commands are operator/debug behavior and
do not conflict with authoring ownership. Mutation commands should either be
dry-run-only or removed until they have an operator-grade use case.

## Acceptance Criteria

- `ergon_builtins` no longer imports `ergon_cli` in production code.
- `ergon_cli` no longer owns real dynamic subtask authoring.
- A builtins-owned agent tool can spawn a toy dynamic child task using
  `WorkerContext.spawn_task(Task(...))`.
- The integration test proves the child is persisted as `is_dynamic=True` with
  full object-bound `task_json`.
- No dynamic child creation path writes `experiment_definition_tasks`.
- The docs and error messages point authors toward
  `WorkerContext.spawn_task(Task(...))`, not CLI graph mutation.
