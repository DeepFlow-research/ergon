# PR 01: Dynamic Subtask Toolkit Ownership

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move agent-facing dynamic subtask authoring out of `ergon_cli` and
prove builtins can spawn object-bound dynamic tasks through
`WorkerContext.spawn_task(Task(...))`.

**Architecture:** `ergon_core.api` owns the runtime facade;
`ergon_builtins.tools` owns agent-facing tools; `ergon_cli` remains a
human/operator adapter.

**Tech Stack:** Pydantic v2, pytest integration tests, WorkerContext,
TaskManagementService, builtins tool factories.

---

## Goal

Move agent-facing dynamic subtask authoring out of `ergon_cli` and into
`ergon_builtins`, backed by the canonical
`WorkerContext.spawn_task(Task(...))` API.

## Source PRDs

- `../prds/01-dynamic-subtask-authoring-toolkit.md`

## Scope

## Current State

- `ergon_builtins.tools.workflow_cli_tool` imports
  `ergon_cli.commands.workflow`.
- The CLI command `workflow manage add-task` looks like dynamic authoring but
  cannot create object-bound tasks.
- `SubtaskLifecycleToolkit` already delegates `add_subtask` to
  `WorkerContext.spawn_task`, but the single-command workflow tool does not.

## Target State For This PR

- Builtins production code has no import dependency on `ergon_cli`.
- A builtins-owned `workflow(command: str)` adapter can spawn a toy dynamic
  child task.
- The child is persisted as a dynamic graph node with full object-bound
  `task_json`.
- The human CLI no longer exposes `workflow manage`.

## Tasks

### Add reusable toy workflow fixtures

Create:

- `ergon_builtins/tests/fixtures/toy_workflow.py`

Work:

- [ ] **Step 1: Create toy public API objects**

  Add test-local Pydantic-compatible classes:

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

- [ ] **Step 2: Add frozen Pydantic harness**

  ```python
  class ToyWorkflowHarness(BaseModel):
      model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

      run_id: UUID
      parent_task_id: UUID
      parent_task: Task
      context: WorkerContext

      def child_task(self, *, task_slug: str, description: str) -> Task: ...
      def nodes(self) -> list[RunGraphNode]: ...
      def edges(self) -> list[RunGraphEdge]: ...
      def definition_tasks(self) -> list[ExperimentDefinitionTask]: ...
  ```

- [ ] **Step 3: Build without external infrastructure**

  The harness must use in-memory/test DB helpers only. It must not require E2B,
  Docker, provider SDKs, or external benchmark assets.

Acceptance:

- The toy task can round-trip through `Task.from_definition`.
- The harness exposes enough row inspection for negative tests.

### Move workflow command adapter into builtins

Create:

- `ergon_builtins/ergon_builtins/tools/workflow_command_adapter.py`
- `ergon_builtins/ergon_builtins/tools/dynamic_task_factory.py`

Modify:

- `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`

Work:

- [ ] **Step 1: Add dynamic task factory**

  Add `dynamic_task_factory.py` with:

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

  Add a default factory that copies the parent task with updated slug,
  description, and `parent_task_slug`.

- [ ] **Step 2: Add builtins command adapter**

  Add `workflow_command_adapter.py` that parses:

  ```text
  inspect resource-list
  inspect resource-content
  inspect task-tree
  inspect task-dependencies
  inspect next-actions
  manage add-subtask --task-slug <slug> --description <description> [--depends-on <node-id> ...]
  ```

- [ ] **Step 3: Inject identity from WorkerContext**

  The model may provide only the command string. The adapter reads run/task
  identity from `WorkerContext`, matching the existing safety property.

- [ ] **Step 4: Reject context escape flags**

  Reject `--run-id`, `--node-id`, `--execution-id`, `--sandbox-task-key`, and
  `--benchmark-type` before any service calls.

- [ ] **Step 5: Update workflow_cli_tool**

  Replace imports from `ergon_cli.commands.workflow` with the builtins adapter.

Acceptance:

- `rg "ergon_cli" ergon_builtins/ergon_builtins/tools` returns no production
  imports.
- The builtins adapter has no direct SQLModel insert path for dynamic nodes or
  edges.

### Delete workflow management from human CLI

Modify:

- `ergon_cli/ergon_cli/commands/workflow.py`

Work:

- [ ] **Step 1: Delete the `manage` parser branch**

  Remove this command family from the human CLI parser:

  ```text
  workflow manage add-task
  workflow manage add-edge
  workflow manage restart-task
  workflow manage abandon-task
  workflow manage materialize-resource
  ```

- [ ] **Step 2: Delete management dispatch**

  Remove `_handle_manage` and the manage branch from workflow command dispatch.
  If resource materialization is still needed by agents, implement it through
  the builtins workflow adapter or a typed builtins tool, not `ergon_cli`.

- [ ] **Step 3: Remove mutation service imports**

  `ergon_cli.commands.workflow` should not import workflow mutation services
  purely to support graph management. Keep only the dependencies needed for
  operator inspection if inspection remains.

- [ ] **Step 4: Add parser rejection test**

  CLI tests must assert `workflow manage ...` is not a valid human CLI command.

Acceptance:

- `ergon_cli` no longer registers `workflow manage`.
- `ergon_cli.commands.workflow` no longer implements `_handle_manage`.
- CLI unit tests prove `workflow manage ...` cannot be parsed/executed through
  the human CLI.
- Builtins integration tests prove `workflow("manage add-subtask ...")` remains
  available to agents.

### Keep typed toolkit path preferred

Modify:

- `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`

Work:

- [ ] **Step 1: Verify typed tool delegation**

  Ensure `SubtaskLifecycleToolkit.add_subtask` calls:

  ```python
  await context.spawn_task(task, depends_on=deps)
  ```

- [ ] **Step 2: Fix stale containment comments**

  Remove comments claiming service-layer containment gaps where
  `WorkerContext` now enforces the rule.

Acceptance:

- Typed lifecycle toolkit and string command adapter both use the same core
  dynamic spawn path.

## Tests

Add:

- `ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py`
- `ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py`

Update:

- `ergon_cli/tests/unit/cli/test_workflow_cli.py`

Required scenarios:

- builtins workflow command spawns a toy dynamic child
- spawned child is `is_dynamic=True`
- spawned child has object-bound `task_json`
- no `ExperimentDefinitionTask` row is written
- context escape flags are rejected
- slug-only dynamic authoring is rejected
- dependency edges are written through core
- cycle-creating dependencies are rejected without partial writes
- non-descendant lifecycle mutation is blocked
- human CLI parser rejects `workflow manage ...`

Run:

```bash
uv run ruff check ergon_cli/ergon_cli ergon_builtins/ergon_builtins
uv run pytest ergon_cli/tests/unit/cli/test_workflow_cli.py
uv run pytest ergon_builtins/tests/integration/tools/test_workflow_command_adapter.py
uv run pytest ergon_builtins/tests/integration/tools/test_subtask_lifecycle_toolkit.py
uv run pytest ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py
```

## PR Ledger

- **Invariant landed:** dynamic subtask authoring is builtins over
  `WorkerContext`, not CLI.
- **Bridge code introduced:** builtins-owned `workflow(command)` adapter.
- **Old path still intentionally alive:** CLI workflow inspection commands.
- **Deletion gate:** PR 06 removes old `ergon_cli.commands.workflow`
  compatibility references.
- **Tests added or updated:** builtins workflow adapter integration tests,
  subtask lifecycle toolkit tests, CLI parser deletion tests.
- **Modules owned by this PR:** `ergon_builtins.tools.workflow_cli_tool`,
  `workflow_command_adapter.py`, `dynamic_task_factory.py`,
  `ergon_cli.commands.workflow`.

## Out Of Scope

- Full workflow inspection rewrite.
- Human CLI domain folder migration.
- Generic command language in core.

## Depends On

- PR 00 is recommended first to reduce workflow CLI churn.
