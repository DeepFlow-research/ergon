# Workflow Agent CLI Implementation Plan

> **Superseded:** this single-file plan has been split into [`workflow-agent-cli/`](workflow-agent-cli/). Start at [`workflow-agent-cli/README.md`](workflow-agent-cli/README.md). Keep this file only as historical context while reviewers migrate.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ergon workflow ...`, an agent-local command surface for the benchmark-task worker to navigate its current workflow topology/resources and explicitly materialize useful visible resources into its workspace without exposing raw SQL.

**Architecture:** Put scoped Postgres queries and resource materialization policy in `ergon_core`, command parsing in `ergon_cli`, and the agent-callable wrapper in `ergon_builtins/tools`. This is not a general operator/debugging CLI: it is invoked by the benchmark agent, runs in the local worker/API process, reads local Postgres directly via `get_session()`, and uses the existing sandbox manager to copy approved resources into the current E2B workspace.

**Tech Stack:** Python, argparse, SQLModel, existing `get_session()` / `ensure_db()`, pydantic-ai `Tool`, pytest.

---

## Package Placement

There is no `arcane_builtins` package in this workspace. The right homes are:

- Core scoped read logic: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_service.py`
- Core materialization policy: `ergon_core/ergon_core/core/runtime/services/workflow_resource_materialization_service.py`
- DTOs: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_dto.py`
- CLI parser and handlers: `ergon_cli/ergon_cli/main.py` and `ergon_cli/ergon_cli/commands/workflow.py`
- Agent wrapper: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Optional worker wiring: initially a target ReAct/research worker, not all workers by default

Keep `ergon_builtins/ergon_builtins/tools/graph_toolkit.py` intact for now. It is resource-discovery-specific and research-named; `workflow` should be more general and command-shaped.

## Resource Ownership and Copy Semantics

Resources are immutable published artifacts. A task may read a visible resource from another task in the same run, including a resource from a different branch of the control DAG, but it must never mutate the source row or source bytes.

The workflow CLI must treat copying as a fork:

- **Read is context.** Reading `resource-content` does not change graph state.
- **Materialize is fork.** Copying a resource into the current agent workspace creates a new `RunResource` row owned by the current task execution.
- **Publish is ownership.** If the current task edits the copied file and publishes it later, the edited artifact is another new resource owned by the current task execution.
- **Lineage is evidence.** The copied resource row records `copied_from_resource_id=<source_resource_id>`, and later edited outputs should preserve provenance in metadata where practical.
- **Control edges schedule work; resource lineage explains information flow.** Materializing a resource from a divergent DAG branch must not add a control dependency edge.

Example:

```text
task_a publishes:
  resource_id=res_a
  task_execution_id=task_a_execution
  name="paper.pdf"
  content_hash=abc

task_b materializes res_a:
  resource_id=res_b_copy
  task_execution_id=task_b_execution
  name="paper (copy).pdf"
  content_hash=abc
  copied_from_resource_id=res_a
  metadata.sandbox_destination="/workspace/imported/task-a/paper (copy).pdf"

task_b edits and publishes:
  resource_id=res_b_edited
  task_execution_id=task_b_execution
  name="paper_annotated.pdf"
  content_hash=def
  metadata.derived_from_resource_ids=["res_a", "res_b_copy"]
```

If task A later republishes a newer `paper.pdf`, task B's copy remains pinned to the old `resource_id` and `content_hash`. Rerun/staleness logic can use resource lineage to flag B as potentially stale, but A never mutates B's copy.

## Code Write Locations

Review this section before implementation. These are the proposed new and modified files.

### New Core Runtime Files

- Create `ergon_core/ergon_core/core/runtime/services/workflow_navigation_dto.py`
  - Owns Pydantic DTOs returned by the workflow inspection service.
  - Intended types: `WorkflowTaskRef`, `WorkflowExecutionRef`, `WorkflowResourceRef`, `WorkflowDependencyRef`, `WorkflowBlockerRef`, `WorkflowNextActionRef`, `WorkflowMaterializedResourceRef`.

- Create `ergon_core/ergon_core/core/runtime/services/workflow_navigation_service.py`
  - Owns scoped Postgres reads for the current run.
  - Implements task listing, task tree traversal, dependency inspection, resource visibility, task blockers, next actions, and resource content reads.
  - Must not query evaluation tables.

- Create `ergon_core/ergon_core/core/runtime/services/workflow_resource_materialization_service.py`
  - Owns the policy-checked "copy visible resource into my current E2B workspace" operation.
  - Reads source `RunResource` metadata/bytes from local Postgres/blob store.
  - Creates a current-task-owned copied `RunResource` row with a new ID.
  - Writes the bytes to the current task sandbox under a controlled workspace path.
  - Records provenance via `copied_from_resource_id` and metadata.

### New Migration File

- Create `ergon_core/migrations/versions/<revision>_add_copied_from_resource_id.py`
  - Adds nullable `run_resources.copied_from_resource_id`.
  - Adds a self-referential foreign key to `run_resources.id`.
  - Adds an index for lineage queries.

### Modified Persistence Files

- Modify `ergon_core/ergon_core/core/persistence/telemetry/models.py`
  - Adds `RunResourceKind.IMPORT`.
  - Adds nullable `RunResource.copied_from_resource_id`.

- Modify `ergon_core/ergon_core/core/persistence/queries.py`
  - Extends `ResourcesQueries.append(...)` to accept `copied_from_resource_id`.
  - Adds small lineage read helpers if needed by workflow inspection/tests.

### New CLI Files

- Create `ergon_cli/ergon_cli/commands/workflow.py`
  - Owns all `ergon workflow inspect ...` and `ergon workflow manage ...` command handlers.
  - Uses `WorkflowNavigationService` for reads.
  - Uses `WorkflowResourceMaterializationService` for `manage materialize-resource`.
  - Uses existing graph/task management services for mutations.
  - Handles text/JSON rendering, `--explain`, output caps, and `--dry-run`.

### Modified CLI Files

- Modify `ergon_cli/ergon_cli/main.py`
  - Imports `handle_workflow`.
  - Registers the top-level `workflow` command.
  - Registers nested `inspect` and `manage` subcommands.
  - Dispatches `args.command == "workflow"` to `handle_workflow(args)`.

### New Builtins Tool File

- Create `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
  - Provides the local pydantic-ai `workflow(command=...)` tool.
  - Injects `WorkerContext.run_id` and `WorkerContext.node_id`.
  - Rejects user-supplied run/experiment/cohort scope arguments.
  - Calls the CLI in-process rather than spawning a shell command.
  - Enforces leaf vs manager command permissions.

### New Proof-of-Concept Worker File

- Create `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`
  - Defines `ResearchRubricsWorkflowCliReActWorker`.
  - Reuses the research-rubrics ReAct/toolkit behavior, but adds the local `workflow(command=...)` tool.
  - Uses worker slug `researchrubrics-workflow-cli-react`.
  - Adds prompt guidance that tells agents to start with `inspect task-tree`, `inspect task-workspace`, `inspect next-actions`, or `inspect resource-list --scope input`.

### Modified Registry File

- Modify `ergon_builtins/ergon_builtins/registry_data.py`
  - Imports `ResearchRubricsWorkflowCliReActWorker`.
  - Registers `"researchrubrics-workflow-cli-react": ResearchRubricsWorkflowCliReActWorker`.
  - Leaves the existing `"researchrubrics-researcher"` worker unchanged.

### New Tests

- Create `tests/unit/runtime/test_workflow_navigation_service.py`
  - Tests core service behavior: current-run reads, immediate-upstream resource semantics, task tree traversal, blockers, next actions, and cross-run resource rejection.

- Create `tests/unit/runtime/test_workflow_resource_materialization_service.py`
  - Tests materialize-resource semantics: same-run visibility, new copied resource ID, copied name, `copied_from_resource_id`, controlled destination path, import manifest, collision handling, and no mutation of the source resource.

- Create `tests/unit/cli/test_workflow_cli.py`
  - Tests parser/handler behavior for `inspect` and `manage` commands.
  - Tests text and JSON output.
  - Tests invalid UUIDs, duplicate slugs, and mutation `--dry-run`.

- Create `tests/unit/state/test_workflow_cli_tool.py`
  - Tests the pydantic-ai wrapper.
  - Verifies scope injection, denial of user-supplied `--run-id`, denial of `inspect resource-list --scope run`, leaf vs manager permissions, multiline rejection, and structured failures.

- Create `tests/unit/runtime/test_workflow_input_resource_semantics.py`
  - Tests the canonical input-resource policy on a diamond and line graph.
  - Ensures a task sees only immediate predecessor resources by default, not transitive ancestors.

### Modified Existing Tests

- Modify `tests/unit/state/test_research_rubrics_workers.py`
  - Adds coverage for `ResearchRubricsWorkflowCliReActWorker`.
  - Asserts the new worker exposes the `workflow` tool.
  - Asserts the existing `ResearchRubricsResearcherWorker` behavior remains unchanged.

- Modify `tests/real_llm/benchmarks/test_researchrubrics.py`
  - Adds environment overrides or a dedicated rollout path for `researchrubrics-workflow-cli-react`.
  - Supports running the final workflow-CLI acceptance rollout with `--limit 5`.
  - Persists enough rollout artifacts to inspect whether and how the agent used `workflow(...)`.

### Files Explicitly Not Planned For V1

- Do not expose eval tables.
- Do not modify dashboard UI files.
- Do not modify `ergon_builtins/ergon_builtins/tools/graph_toolkit.py`; keep it as the existing research/resource toolkit.
- Do not add E2B-side CLI execution or require E2B-to-localhost networking.

## Command Surface

Build two explicit command groups:

- `workflow inspect ...`: read-only task topology, dependency, resource, and workspace inspection.
- `workflow manage ...`: state-changing task/dependency management commands that wrap the existing task lifecycle services.

The command surface is intended for the currently executing benchmark-task agent. It reads Postgres directly through scoped services, but the model never receives a SQL console and never selects another run.

Every command is scoped by injected runtime context:

- `run_id`: injected from `WorkerContext.run_id`
- `node_id`: injected from `WorkerContext.node_id`
- `execution_id`: available to the wrapper from `WorkerContext.execution_id` if needed later

For direct developer testing, `ergon workflow ...` may still accept explicit `--run-id` and `--node-id`, but that is test/debug plumbing. The agent wrapper strips or rejects user-supplied scope arguments and supplies the real values.

Keep mutation commands out of `inspect`. If a command changes graph state, it belongs under `manage` and should return an explicit mutation result.

All commands should support `--format text|json` (default `text`) and `--explain` (adds a short explanation of the scope/policy being applied). Commands that can produce large output should also support caps: `--limit`, `--max-chars`, or `--max-bytes` as appropriate.

All `manage ...` commands must support `--dry-run`. Dry-run resolves slugs to node IDs, checks visibility and service preconditions, and prints the mutation that would happen without writing to Postgres or emitting events.

## Inspect Commands

### `workflow inspect task-list`

Lists task nodes in a run.

Examples:

```bash
workflow("inspect task-list")
workflow("inspect task-list --children")
workflow("inspect task-list --level 2")
workflow("inspect task-list --under d_root --level 3")
workflow("inspect task-list --format json")
```

Behavior:

- Reads `RunGraphNode` rows for the run.
- `--children` restricts to direct children of the current node.
- `--level N` returns tasks at absolute graph level `N`.
- `--under TASK_SLUG_OR_NODE_ID --level N` returns tasks at relative level `N` inside that subtree.
- `--status STATUS` filters by node status.
- Table columns: `node_id_short`, `task_slug`, `status`, `level`, `parent_node_id_short`, `worker`.
- JSON output returns full IDs and the same fields.
- Does not read evaluations or context events.

### `workflow inspect task-tree`

Shows a recursive task subtree, grouped by level. This should be the default orientation command for agents because it behaves like a mixture of `cd` and `ls`, but with a self-describing name.

Examples:

```bash
workflow("inspect task-tree")
workflow("inspect task-tree --from current --depth 2")
workflow("inspect task-tree --from root --depth 3")
workflow("inspect task-tree --from d_root --level 2")
workflow("inspect task-tree --from d_root --status pending")
```

Behavior:

- `--from current` starts at the current node; this is the default.
- `--from root` starts at the root node for the current run.
- `--from TASK_SLUG_OR_NODE_ID` starts at that node.
- `--depth N` prints descendants up to `N` levels below the start node.
- `--level N` prints only descendants at relative level `N` below the start node.
- Uses `parent_node_id` containment, not dependency edges.

Example output:

```text
TREE from=parent depth=2

level +0
  parent        running    node=9af1c2aa worker=researchrubrics-smoke-worker

level +1
  d_root        completed  node=8a31c4f2 worker=researchrubrics-smoke-leaf
  l_1           completed  node=0c72d1aa worker=researchrubrics-smoke-leaf
  s_a           completed  node=f71e5a10 worker=researchrubrics-smoke-leaf

level +2
  d_left        completed  node=19de72aa parent=d_root worker=researchrubrics-smoke-leaf
  d_right       completed  node=34b7a901 parent=d_root worker=researchrubrics-smoke-leaf
  l_2           pending    node=aa10e821 parent=l_1 worker=researchrubrics-smoke-leaf
```

For "show every task on this level recursive down", the agent uses:

```bash
workflow("inspect task-tree --from current --level 2")
```

### `workflow inspect task-details`

Shows one task node plus latest execution summary.

Examples:

```bash
workflow("inspect task-details")
workflow("inspect task-details --task-slug d_left --include-output")
workflow("inspect task-details --task-slug d_left --format json")
```

Behavior:

- With no selector, shows the current node.
- With `--task-slug`, resolves exactly one node in the current run.
- If `--task-slug` matches multiple nodes in a run, exits non-zero and prints the matching node IDs.
- Includes latest `RunTaskExecution` status, attempt number, timestamps, and resource count.
- `--include-output` includes a truncated `final_assistant_message`, default max 1200 chars, configurable with `--max-chars`.
- Does not expose evaluation feedback.

### `workflow inspect task-dependencies`

Shows graph dependencies for a task.

Examples:

```bash
workflow("inspect task-dependencies")
workflow("inspect task-dependencies --task-slug d_join --direction upstream")
workflow("inspect task-dependencies --task-slug d_left --direction downstream --format json")
```

Behavior:

- Reads `RunGraphEdge`.
- `--direction upstream` lists incoming edges: source task -> current task.
- `--direction downstream` lists outgoing edges: current task -> target task.
- `--direction both` lists both.
- Table columns: `direction`, `edge_status`, `source_slug`, `source_status`, `target_slug`, `target_status`, `edge_id_short`.

### `workflow inspect task-blockers`

Explains why a task is not ready, not completed, or cannot proceed.

Examples:

```bash
workflow("inspect task-blockers")
workflow("inspect task-blockers --task-slug d_join")
workflow("inspect task-blockers --task-slug l_3 --format json")
```

Behavior:

- Defaults to current node.
- Reports unsatisfied upstream dependencies, failed upstream dependencies, blocked/cancelled status, running children, and missing input resources if inferable.
- Does not mutate anything.
- Includes suggested next inspection commands.

Example output:

```text
Task blockers: d_join

Readiness:
  blocked: yes
  reason: waiting_for_upstream

Upstream dependencies:
  d_left   completed   edge=satisfied   resources=2
  d_right  running     edge=pending     resources=0

Next useful commands:
  workflow("inspect task-details --task-slug d_right")
  workflow("inspect resource-list --scope input")
```

### `workflow inspect next-actions`

Gives the agent a concise recovery/orientation summary for the current visible run scope.

Examples:

```bash
workflow("inspect next-actions")
workflow("inspect next-actions --include-completed")
```

Behavior:

- Lists ready, pending, blocked, failed, and cancelled tasks visible to the current agent.
- Suggests concrete commands to inspect or manage the highest-priority items.
- For leaf agents, suggestions include only `inspect ...` commands.
- For manager-capable agents, suggestions may include `manage ... --dry-run` commands.

Example output:

```text
Next actions

Blocked:
  l_3 blocked because l_2 failed
    inspect: workflow("inspect task-details --task-slug l_2 --include-output")
    manager dry-run: workflow("manage restart-task --task-slug l_2 --dry-run")

Ready:
  d_join has all upstream inputs satisfied
    inspect: workflow("inspect task-workspace --task-slug d_join")

Input resources:
  current task has 4 input resources
    inspect: workflow("inspect resource-list --scope input")
```

### `workflow inspect resource-list`

Lists visible resources.

Examples:

```bash
workflow("inspect resource-list --scope input")
workflow("inspect resource-list --scope upstream")
workflow("inspect resource-list --scope children")
workflow("inspect resource-list --scope descendants --max-depth 3")
workflow("inspect resource-list --scope visible --limit 20")
workflow("inspect resource-list --scope own --kind report")
workflow("inspect resource-list --scope input --format json")
```

Scopes:

- `input`: resources produced by latest successful executions of immediate upstream dependency nodes. This is the default for task-scoped agents.
- `upstream`: same as `input` for v1; kept as a readable alias.
- `own`: resources produced by the current node's latest execution.
- `children`: resources produced by direct child task executions.
- `descendants`: resources produced by descendants up to `--max-depth`, default 3.
- `visible`: same-run resources the current profile is allowed to see, including resources from divergent DAG branches. This is needed for opportunistic collaboration, but it must still exclude eval/private/system resources and be capped by `--limit`.
- `run`: do not expose in v1. Even current-run-wide raw resources are broader than a benchmark-task agent needs by default.

Table columns: `resource_id_short`, `kind`, `name`, `task_slug`, `size_bytes`, `mime_type`, `created_at`, `content_hash_short`.

### `workflow inspect resource-content`

Reads resource content from the blob path stored in `RunResource.file_path`.

Examples:

```bash
workflow("inspect resource-content --resource-id $RESOURCE_ID")
workflow("inspect resource-content --resource-id $RESOURCE_ID --max-bytes 20000")
```

Behavior:

- Verifies the resource belongs to the injected current `run_id`.
- Verifies resource ID is visible under the active scope policy before reading bytes.
- Reads bytes from `RunResource.file_path`.
- If bytes decode as UTF-8, prints text.
- If not UTF-8, prints a short binary summary and exits 0 unless `--raw` is supplied later.
- Caps output with `--max-bytes`, default 64 KiB.

### `workflow inspect resource-location`

Returns metadata and local blob path for a resource without dumping content.

Example:

```bash
workflow("inspect resource-location --resource-id $RESOURCE_ID")
```

Behavior:

- Useful for humans and tests.
- Agent wrapper may hide `file_path` if path leakage becomes a concern; v1 can expose it because it is a host blob path and already part of resource metadata.

### `workflow inspect task-workspace`

Shows the full task workspace snapshot: task, execution, upstream dependencies, downstream dependents, input resources, own resources, children, and suggested next commands.

Examples:

```bash
workflow("inspect task-workspace")
workflow("inspect task-workspace --task-slug d_join")
workflow("inspect task-workspace --task-slug d_join --include-output")
```

Behavior:

- Defaults to current node.
- Uses only current-run data.
- No evaluation rows.
- Output should be compact and sectioned so the agent can orient in one call.

## Manage Commands

`manage` means "state-changing", not necessarily "manager-only".

- Graph lifecycle commands require a manager-capable wrapper profile: create/restart/abandon/update task graph state.
- `manage materialize-resource` is a current-task workspace/import operation and should be available to ordinary task agents when the source resource is visible under policy.

### `workflow manage create-task`

Adds one dynamic subtask under the current node by wrapping `TaskManagementService.add_subtask`.

Examples:

```bash
workflow("manage create-task --task-slug summarize_left --worker researchrubrics-smoke-leaf --description 'Summarize left branch'")
workflow("manage create-task --task-slug join --worker researchrubrics-smoke-leaf --description 'Join summaries' --depends-on summarize_left --depends-on summarize_right")
workflow("manage create-task --task-slug join --worker researchrubrics-smoke-leaf --description 'Join summaries' --depends-on summarize_left --dry-run")
```

Behavior:

- Parent is always the current node unless a privileged manager profile later allows `--parent`.
- Creates a `RunGraphNode` with `parent_node_id=current_node_id`.
- Creates dependency edges for `--depends-on` slugs/node IDs.
- Returns created node ID, slug, and status.
- With `--dry-run`, validates parent, dependency references, and worker slug, then prints the proposed node and edges without writing.

### `workflow manage create-task-plan`

Adds multiple dynamic subtasks in one transaction by wrapping `TaskManagementService.plan_subtasks`.

Examples:

```bash
workflow("manage create-task-plan --json '[{\"task_slug\":\"a\",\"description\":\"Do A\",\"assigned_worker_slug\":\"researchrubrics-smoke-leaf\"},{\"task_slug\":\"b\",\"description\":\"Do B\",\"assigned_worker_slug\":\"researchrubrics-smoke-leaf\",\"depends_on\":[\"a\"]}]'")
workflow("manage create-task-plan --json '[{\"task_slug\":\"a\",\"description\":\"Do A\",\"assigned_worker_slug\":\"researchrubrics-smoke-leaf\"}]' --dry-run")
```

Behavior:

- This is the safest way to add a local DAG.
- Rejects cycles/duplicates through existing service validation.
- Returns created nodes and root slugs.
- With `--dry-run`, runs the same validation and returns the normalized plan without inserting nodes.

### `workflow manage create-dependency`

Adds a dependency edge between two existing sibling/visible tasks.

Examples:

```bash
workflow("manage create-dependency --source summarize_left --target join")
workflow("manage create-dependency --source summarize_left --target join --dry-run")
```

Behavior:

- Uses `WorkflowGraphRepository.add_edge`.
- Source and target must resolve inside the current run and be visible to the current agent profile.
- Fails if the edge would create a cycle.
- New edge status starts as `pending`.
- With `--dry-run`, resolves source/target and checks cycle risk without adding the edge.

### `workflow manage restart-task`

Resets a terminal task back to pending by wrapping `TaskManagementService.restart_task`.

Examples:

```bash
workflow("manage restart-task --task-slug l_2")
workflow("manage restart-task --node-id aa10e821-...")
workflow("manage restart-task --task-slug l_2 --dry-run")
```

Behavior:

- Only terminal tasks can be reset.
- Existing service handles downstream invalidation/reset behavior.
- Returns old status and invalidated downstream node IDs.
- With `--dry-run`, reports whether the task is restartable and which downstream nodes would be invalidated.

### `workflow manage abandon-task`

Abandons/cancels a task by wrapping `TaskManagementService.cancel_task`.

Examples:

```bash
workflow("manage abandon-task --task-slug l_3")
workflow("manage abandon-task --node-id 98db73a2-...")
workflow("manage abandon-task --task-slug l_3 --dry-run")
```

Behavior:

- Transitions the target to cancelled when allowed.
- Emits the existing cancellation event through the service path.
- Returns old status and cascade count.
- With `--dry-run`, reports whether cancellation is allowed and the descendant cascade count without writing or emitting events.

### `workflow manage update-task-description`

Updates a non-running task description by wrapping `TaskManagementService.refine_task`.

Examples:

```bash
workflow("manage update-task-description --task-slug l_3 --description 'Retry with the corrected input file'")
workflow("manage update-task-description --task-slug l_3 --description 'Retry with the corrected input file' --dry-run")
```

Behavior:

- Fails on running tasks.
- Returns old and new description.
- With `--dry-run`, validates mutability and prints the old/new description without writing.

### `workflow manage materialize-resource`

Copies one immutable, visible `RunResource` from local Postgres/blob storage into the current agent's E2B workspace and records the copy as a new current-task-owned resource.

This is a fork operation, not a mutation of the source task's artifact.

Examples:

```bash
workflow("manage materialize-resource --resource-id $RESOURCE_ID")
workflow("manage materialize-resource --resource-id $RESOURCE_ID --destination imported/task-a/paper.pdf")
workflow("manage materialize-resource --resource-id $RESOURCE_ID --destination imported/task-a/paper.pdf --dry-run")
```

Behavior:

- Resolves `--resource-id` to a source `RunResource` in the current run.
- Requires the source resource to be visible to the current agent profile.
- Rejects evaluation/private/system resources and cross-run resource IDs.
- Reads bytes from the source resource's content-addressed `file_path`.
- Writes bytes into the current E2B sandbox under `/workspace/<destination>`.
- If `--destination` is omitted, uses a collision-safe default like `/workspace/imported/<producer-task-slug>/<resource name (copy).ext>`.
- Rejects absolute destinations, `..`, symlink escapes, and paths outside `/workspace`.
- Creates a new `RunResource` row owned by the current task execution:
  - new `id`
  - `task_execution_id=current_execution_id`
  - `kind=import`
  - `name="<source name> (copy)<ext>"` unless an explicit destination name is provided
  - same `file_path` and `content_hash` as the source resource
  - `copied_from_resource_id=<source resource id>`
  - metadata containing source task/node identifiers, source name/hash, sandbox destination, and materialized timestamp
- Updates `/workspace/.ergon/resource_imports.json` in the sandbox with the source resource ID, copied resource ID, content hash, and destination path so future tools/debuggers can reconstruct the local workspace import history.
- Does not add a control edge to the DAG.
- With `--dry-run`, validates source visibility, destination normalization, collision behavior, sandbox target, and the copied resource name without writing to Postgres or E2B.

Ordering:

- Validate source visibility and destination before side effects.
- Write bytes to the sandbox destination first.
- Append the copied `RunResource` row only after the sandbox write succeeds.
- Update the import manifest after the copied row exists so it can include the new copied resource ID.
- If the manifest update fails after the file copy/resource row succeeds, return a structured warning rather than pretending the source was not materialized.

V1 lineage boundary:

- The materialized copy row has strong lineage via `copied_from_resource_id`.
- Arbitrary later edits are B-owned outputs. They must never mutate A's row.
- Do not pretend to infer every arbitrary transformation automatically in v1. If the edited output is later published, it is enough that the run has the materialization row, the import manifest, and the tool-call context events to explain how B got the source bytes. A richer many-to-many `run_resource_lineage` table can come later if synthesis from multiple copied resources becomes central.

Output:

```text
materialized resource
  source: res_a paper.pdf sha256:abc...
  copy:   res_b paper (copy).pdf kind=import
  copied_from_resource_id: res_a
  sandbox_path: /workspace/imported/task-a/paper (copy).pdf
  note: source resource was not modified
```

JSON output should include at least:

```json
{
  "source_resource_id": "res_a",
  "copied_resource_id": "res_b",
  "copied_from_resource_id": "res_a",
  "source_content_hash": "abc",
  "copied_content_hash": "abc",
  "sandbox_path": "/workspace/imported/task-a/paper (copy).pdf",
  "source_mutated": false
}
```

## Deferred Commands

Do not build these in v1:

- `ergon workflow messages send`: useful workflow primitive, but not needed for the first read/navigation surface.
- Arbitrary `manage remove-dependency`: higher risk than `create-dependency` because it can unexpectedly unblock or strand work; add after mutation auditing is clearer.

## Agent Invocation Model

The agent runs locally in the worker process. The environment runs in E2B. Therefore this command surface should read local Postgres directly, then let existing sandbox tools handle E2B environment actions. Do not put this command inside the E2B sandbox.

The model must not pass, override, or discover `--run-id`; the wrapper injects the current `WorkerContext.run_id`. The model also must not inspect other runs in the same experiment, cohort, benchmark, or different experiments.

### Single Tool Path

Create `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py` with:

```python
def make_workflow_cli_tool(
    *,
    context: WorkerContext,
    allowed_scopes: frozenset[str] = frozenset({"input", "own", "upstream", "children", "descendants", "visible"}),
    manager_capable: bool = False,
) -> Callable[..., Awaitable[WorkflowCliToolResponse]]:
    ...
```

The pydantic-ai tool signature should be:

```python
async def workflow(command: str, timeout_s: int = 10) -> WorkflowCliToolResponse:
    """Run a scoped workflow navigation command, for example:
    `inspect task-tree`, `inspect task-details --task-slug d_left`,
    `inspect task-dependencies --task-slug d_join`,
    `inspect resource-list --scope input`, `inspect resource-content --resource-id ...`,
    `manage materialize-resource --resource-id ...`,
    or manager-profile commands like `manage restart-task --task-slug l_2`.
    `run_id`, current `node_id`, current `execution_id`, and sandbox context
    are injected automatically.
    """
```

Important behavior:

- The model passes only the subcommand string, e.g. `inspect resource-list --scope input`.
- The wrapper prepends `workflow` and injects `--run-id <context.run_id>`, `--node-id <context.node_id>`, `--execution-id <context.execution_id>`, `--sandbox-id <context.sandbox_id>`, and `--sandbox-task-key <context.task_id or context.node_id>` when the command supports them.
- The wrapper rejects any user-supplied `--run-id`, `--node-id`, `--execution-id`, `--sandbox-id`, `--sandbox-task-key`, `--definition-id`, `--experiment-id`, or `--cohort-id` argument in v1. Current-run/current-task scope is an invariant, not a prompt instruction.
- The wrapper calls the CLI handler in-process via `ergon_cli.main._main(argv)` with stdout/stderr captured, not via subprocess.
- The wrapper rejects disallowed tokens in v1: shell metacharacters are irrelevant for in-process argv parsing, but still reject newlines and commands starting with `run`, `eval`, `doctor`, etc.
- The wrapper does not allow `inspect resource-list --scope run`.

### Bash Path

For local agents, the "bash" path should mean local command execution, not the current E2B sandbox bash tool. The existing `bash_sandbox_tool.py` runs inside E2B and cannot see local Postgres.

Two options:

- Preferred v1: use the single `workflow(command=...)` tool.
- Later: add a local bash-like tool that only whitelists `ergon workflow ...`, but do not mix it with E2B bash.

System prompt guidance for ReAct agents should say:

```text
Use the `workflow` tool to inspect the workflow run graph and resources.
Start with `inspect task-tree`, `inspect task-workspace`, `inspect next-actions`, or `inspect resource-list --scope input`.
Do not assume transitive dependencies are inputs; use `inspect task-dependencies` if unsure.
Use `manage materialize-resource --resource-id ... --dry-run` before importing a useful resource into your workspace.
Before mutating the task graph, run the same graph-lifecycle `manage ...` command with `--dry-run`.
```

## Permissions Model

V1 policy is simple and explicit:

- Agent wrapper: automatically scoped to one `run_id` and current `node_id`; the model cannot choose a run.
- Direct CLI invocation with explicit IDs exists only for developer tests/debugging, not as a model-facing capability.
- Agent wrapper default read scopes: `input`, `own`, `upstream`, `children`, `descendants`, `visible`.
- Agent wrapper same-run collaboration scope: `visible`, capped by `--limit`, for resources from divergent branches that are useful context but not control dependencies.
- Agent wrapper denied scope: `run`.
- Agent wrapper denied cross-run scope: other runs from the same experiment, cohort, benchmark, or other experiments.
- Graph mutation commands require a manager-capable profile. Manager agents may get `manage create-task`, `manage create-task-plan`, `manage create-dependency`, `manage restart-task`, `manage abandon-task`, and `manage update-task-description`.
- Resource materialization is allowed for leaf and manager agents, but only for visible same-run resources and only into the current task sandbox/workspace.
- Manager-capable agents should be instructed to use `--dry-run` before every non-trivial mutation. V1 enforces support for dry-run but does not require a confirm token.
- No eval tables are queried by any command.
- No raw SQL is accepted.

Later profiles can be layered on top:

- `leaf`: input, own, upstream summaries, and capped same-run visible resource discovery/materialization.
- `manager`: children, descendants, task lifecycle mutations.
- `evaluator`: target task outputs only.
- `cohort_observer` / `meta_analyst`: cross-run summaries without raw resource content and without evaluation leakage, only if explicitly assigned.

Future safety layer:

- `--confirm-token` for destructive mutations. A dry run would produce a short token that must be echoed back on the real command. Do not build this in v1 unless mutation behavior proves too risky in tests.

## Implementation File Plan

This is the master file/folder plan for implementation.

### Added Files

```text
ergon_core/
  migrations/
    versions/
      <revision>_add_copied_from_resource_id.py
  ergon_core/
    core/
      runtime/
        services/
          workflow_navigation_dto.py
          workflow_navigation_service.py
          workflow_resource_materialization_service.py

ergon_cli/
  ergon_cli/
    commands/
      workflow.py

ergon_builtins/
  ergon_builtins/
    tools/
      workflow_cli_tool.py
    workers/
      research_rubrics/
        workflow_cli_react_worker.py

tests/
  unit/
    runtime/
      test_workflow_navigation_service.py
      test_workflow_input_resource_semantics.py
      test_workflow_resource_materialization_service.py
    cli/
      test_workflow_cli.py
    state/
      test_workflow_cli_tool.py
```

### Edited Files

```text
ergon_cli/
  ergon_cli/
    main.py

ergon_core/
  ergon_core/
    core/
      persistence/
        telemetry/
          models.py
        queries.py

ergon_builtins/
  ergon_builtins/
    registry_data.py

tests/
  unit/
    state/
      test_research_rubrics_workers.py
  real_llm/
    benchmarks/
      test_researchrubrics.py
```

`ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py` is intentionally not edited for the POC path.

### Deleted Files

```text
(none)
```

### Optional Edited Files If We Include Automatic Sandbox Input Threading Now

```text
ergon_core/
  ergon_core/
    api/
      worker_context.py
    core/
      runtime/
        inngest/
          execute_task.py
        services/
          orchestration_dto.py
          task_execution_service.py
```

These optional edits are only for automatic input materialization at sandbox creation time. They are separate from `workflow manage materialize-resource`, which is an explicit on-demand copy/fork operation initiated by the current agent.

## Task 0: Add Resource Copy Lineage Schema

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/queries.py`
- Create: `ergon_core/migrations/versions/<revision>_add_copied_from_resource_id.py`

- [ ] **Step 1: Add failing persistence tests**

Add focused tests that create a source `RunResource`, append a copied resource, and assert:

- copied row has a new `id`
- copied row keeps the same `content_hash` and `file_path`
- copied row has `kind="import"`
- copied row has `copied_from_resource_id=<source id>`
- source row is unchanged

- [ ] **Step 2: Update `RunResourceKind` and `RunResource`**

File path: `ergon_core/ergon_core/core/persistence/telemetry/models.py`

```python
class RunResourceKind(StrEnum):
    OUTPUT = "output"
    REPORT = "report"
    ARTIFACT = "artifact"
    SEARCH_CACHE = "search_cache"
    NOTE = "note"
    IMPORT = "import"
    """Copied snapshot materialized from another RunResource into a task workspace."""

class RunResource(SQLModel, table=True):
    # ...
    copied_from_resource_id: UUID | None = Field(
        default=None,
        foreign_key="run_resources.id",
        index=True,
    )
```

- [ ] **Step 3: Update resource append helper**

File path: `ergon_core/ergon_core/core/persistence/queries.py`

Extend `ResourcesQueries.append(...)` with:

```python
copied_from_resource_id: UUID | None = None
```

and pass it to `RunResource(...)`.

- [ ] **Step 4: Add migration**

File path: `ergon_core/migrations/versions/<revision>_add_copied_from_resource_id.py`

Migration behavior:

- `upgrade()` adds nullable `copied_from_resource_id` UUID column to `run_resources`
- creates a self-referential foreign key to `run_resources.id`
- creates an index on `run_resources.copied_from_resource_id`
- `downgrade()` drops index, foreign key, and column

Run:

```bash
pytest tests/unit/runtime/test_workflow_resource_materialization_service.py -v
```

Expected: schema/helper tests pass once the materialization service is implemented.

## Task 1: Add Workflow Navigation DTOs and Service

**Files:**

- Create: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_dto.py`
- Create: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_service.py`
- Create: `ergon_core/ergon_core/core/runtime/services/workflow_resource_materialization_service.py`
- Test: `tests/unit/runtime/test_workflow_navigation_service.py`
- Test: `tests/unit/runtime/test_workflow_resource_materialization_service.py`

- [ ] **Step 1: Write failing service tests**

Add tests for:

- `list_tasks(run_id)` returns all run nodes ordered by level/task_slug.
- `list_tasks(run_id, parent_node_id=...)` returns direct children only.
- `list_deps(..., direction="upstream")` returns incoming edges with source/target summaries.
- `list_resources(..., scope="input")` returns resources from latest completed executions of immediate upstream nodes only.
- `list_resources(..., scope="visible")` can include same-run resources from divergent branches while still excluding cross-run/eval/private resources.
- `get_resource_content` rejects a resource from a different run.
- `get_task_blockers(...)` reports pending upstream dependencies and failed upstream dependencies.
- `get_next_actions(...)` suggests inspect-only commands for leaf profiles and dry-run manage commands for manager profiles.
- `materialize_resource(...)` creates a new current-task-owned `kind=import` resource row with a new ID, copied name, same hash/blob path, and `copied_from_resource_id`.
- `materialize_resource(...)` writes or updates `/workspace/.ergon/resource_imports.json` in the sandbox with source/copy/destination metadata.
- `materialize_resource(..., dry_run=True)` validates source/destination without writing to Postgres or E2B.
- `materialize_resource(...)` rejects cross-run resources, invisible resources, absolute destinations, `..`, and destination collisions unless overwrite/versioning behavior is explicit.

Use a tiny graph fixture:

```text
a -> b -> c
x
```

Give `a`, `b`, and `x` one completed execution each; give `a` and `b` one resource each. Assert `c` input resources include only `b` resource, not `a`.

- [ ] **Step 2: Implement DTOs**

Define frozen Pydantic models:

File path: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_dto.py`

```python
class WorkflowTaskRef(BaseModel):
    model_config = {"frozen": True}
    node_id: UUID
    task_slug: str
    status: str
    level: int
    parent_node_id: UUID | None = None
    assigned_worker_slug: str | None = None

class WorkflowExecutionRef(BaseModel):
    model_config = {"frozen": True}
    execution_id: UUID
    status: str
    attempt_number: int
    final_assistant_message: str | None = None

class WorkflowResourceRef(BaseModel):
    model_config = {"frozen": True}
    resource_id: UUID
    run_id: UUID
    task_execution_id: UUID | None
    node_id: UUID | None
    task_slug: str | None
    kind: str
    name: str
    mime_type: str
    size_bytes: int
    file_path: str
    content_hash: str | None = None
    copied_from_resource_id: UUID | None = None
    created_at: datetime

class WorkflowDependencyRef(BaseModel):
    model_config = {"frozen": True}
    edge_id: UUID
    edge_status: str
    source: WorkflowTaskRef
    target: WorkflowTaskRef

class WorkflowBlockerRef(BaseModel):
    model_config = {"frozen": True}
    task: WorkflowTaskRef
    reason: str
    details: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)

class WorkflowNextActionRef(BaseModel):
    model_config = {"frozen": True}
    priority: str
    task: WorkflowTaskRef | None = None
    summary: str
    suggested_commands: list[str] = Field(default_factory=list)

class WorkflowMaterializedResourceRef(BaseModel):
    model_config = {"frozen": True}
    source_resource_id: UUID
    copied_resource_id: UUID | None
    copied_from_resource_id: UUID
    source_name: str
    copied_name: str
    source_content_hash: str | None
    copied_content_hash: str | None
    sandbox_path: str
    dry_run: bool = False
    source_mutated: bool = False
```

- [ ] **Step 3: Implement read service**

Implement `WorkflowNavigationService` methods:

File path: `ergon_core/ergon_core/core/runtime/services/workflow_navigation_service.py`

```python
class WorkflowNavigationService:
    def list_tasks(self, session: Session, *, run_id: UUID, parent_node_id: UUID | None = None) -> list[WorkflowTaskRef]: ...
    def get_task(self, session: Session, *, run_id: UUID, node_id: UUID | None, task_slug: str | None) -> WorkflowTaskRef: ...
    def get_latest_execution(self, session: Session, *, node_id: UUID) -> RunTaskExecution | None: ...
    def list_dependencies(self, session: Session, *, run_id: UUID, node_id: UUID, direction: Literal["upstream", "downstream", "both"]) -> list[WorkflowDependencyRef]: ...
    def list_resources(self, session: Session, *, run_id: UUID, node_id: UUID | None, scope: Literal["input", "upstream", "own", "children", "descendants", "visible", "run"], kind: str | None = None, max_depth: int = 3, limit: int = 50) -> list[WorkflowResourceRef]: ...
    def read_resource_bytes(self, session: Session, *, run_id: UUID, resource_id: UUID, max_bytes: int) -> bytes: ...
    def get_task_blockers(self, session: Session, *, run_id: UUID, node_id: UUID) -> list[WorkflowBlockerRef]: ...
    def get_next_actions(self, session: Session, *, run_id: UUID, node_id: UUID, manager_capable: bool) -> list[WorkflowNextActionRef]: ...
```

For `input` / `upstream`, use incoming edges to the current node, get each source node's latest completed execution, then collect `RunResource` rows for those execution IDs.

Implement `WorkflowResourceMaterializationService` separately from read-only navigation:

File path: `ergon_core/ergon_core/core/runtime/services/workflow_resource_materialization_service.py`

```python
class WorkflowResourceMaterializationService:
    async def materialize_resource(
        self,
        session: Session,
        *,
        run_id: UUID,
        current_node_id: UUID,
        current_execution_id: UUID,
        sandbox_task_key: UUID,
        benchmark_type: str,
        resource_id: UUID,
        destination: str | None,
        dry_run: bool,
    ) -> WorkflowMaterializedResourceRef: ...
```

The service should use the benchmark's sandbox manager class and existing `BaseSandboxManager.upload_file(...)` to write into the live E2B sandbox. It should not create a new low-level E2B upload primitive.

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/unit/runtime/test_workflow_navigation_service.py tests/unit/runtime/test_workflow_resource_materialization_service.py -v
```

Expected: all tests pass.

## Task 2: Add `ergon workflow` CLI Commands

**Files:**

- Create: `ergon_cli/ergon_cli/commands/workflow.py`
- Modify: `ergon_cli/ergon_cli/main.py`
- Test: `tests/unit/cli/test_workflow_cli.py`

- [ ] **Step 1: Write failing parser/handler tests**

Add tests that call `handle_workflow(args)` directly and at least one parser integration test using `build_parser().parse_args(...)`.

Test cases:

- `ergon workflow inspect task-list --run-id <id>` renders slugs.
- `ergon workflow inspect task-details --run-id <id> --task-slug b --include-output` renders latest output excerpt.
- `ergon workflow inspect task-dependencies --run-id <id> --task-slug c --direction upstream` renders `b -> c`.
- `ergon workflow inspect resource-list --run-id <id> --node-id <c> --scope input` includes `b` resource only.
- `ergon workflow inspect resource-content --run-id <id> --resource-id <rid>` prints file content.
- `ergon workflow inspect task-blockers --run-id <id> --node-id <blocked>` explains why a task is blocked.
- `ergon workflow inspect next-actions --run-id <id> --node-id <manager>` prints suggested commands.
- `ergon workflow manage materialize-resource --run-id <id> --node-id <b> --execution-id <exec_b> --sandbox-task-key <task-or-node> --resource-id <rid> --destination imported/a/report.pdf --dry-run` reports the copy/fork without DB or E2B writes.
- `ergon workflow manage materialize-resource ...` creates a new `kind=import` resource row with `copied_from_resource_id` and writes the file to `/workspace/imported/a/report (copy).pdf`.
- Every `manage ... --dry-run` command validates and reports the planned mutation without DB writes.
- invalid UUID returns exit code 1.
- duplicate `--task-slug` returns exit code 1 and helpful message.

- [ ] **Step 2: Register parser**

In `ergon_cli/ergon_cli/main.py`:

- Import `handle_workflow`.
- Add top-level `workflow`.
- Add nested subcommands:
  - `inspect task-list`
  - `inspect task-tree`
  - `inspect task-details`
  - `inspect task-dependencies`
  - `inspect task-blockers`
  - `inspect next-actions`
  - `inspect resource-list`
  - `inspect resource-content`
  - `inspect resource-location`
  - `inspect task-workspace`
  - `manage create-task`
  - `manage create-task-plan`
  - `manage create-dependency`
  - `manage restart-task`
  - `manage abandon-task`
  - `manage update-task-description`
  - `manage materialize-resource`
- Add branch:

File path: `ergon_cli/ergon_cli/main.py`

```python
elif args.command == "workflow":
    return handle_workflow(args)
```

- [ ] **Step 3: Implement handler**

In `commands/workflow.py`, implement:

File path: `ergon_cli/ergon_cli/commands/workflow.py`

```python
def handle_workflow(args: Namespace) -> int:
    ensure_db()
    ...
```

Use `WorkflowNavigationService`, `WorkflowResourceMaterializationService`, `get_session()`, `render_table`, and `json.dumps(..., default=str)` for `--format json`.

Keep output agent-friendly:

- Plain table by default.
- Compact JSON when requested.
- No rich formatting.
- Stable field names.

- [ ] **Step 4: Run CLI tests**

Run:

```bash
pytest tests/unit/cli/test_workflow_cli.py -v
```

Expected: all tests pass.

## Task 3: Add Agent-Facing Workflow CLI Tool

**Files:**

- Create: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Test: `tests/unit/state/test_workflow_cli_tool.py`

- [ ] **Step 1: Write failing wrapper tests**

Test cases:

- `workflow("inspect task-list")` injects `--run-id` and returns stdout/exit code.
- `workflow("inspect resource-list --scope input")` injects `--node-id`.
- `workflow("inspect resource-list --scope visible --limit 20")` is allowed for same-run collaboration discovery.
- `workflow("inspect resource-list --scope run")` is denied by default.
- `workflow("manage materialize-resource --resource-id <rid> --destination imported/a/report.pdf --dry-run")` is allowed for leaf wrappers and injects current execution/sandbox context.
- `workflow("manage restart-task --task-slug l_2 --dry-run")` is allowed only for manager-capable wrappers.
- `workflow("manage restart-task --task-slug l_2")` is denied for leaf wrappers.
- User-supplied `--execution-id`, `--sandbox-id`, or `--sandbox-task-key` is rejected.
- `workflow("../bad")` or multiline input is rejected.
- Non-zero CLI exit returns a structured failure, not an exception.

- [ ] **Step 2: Implement response DTOs**

Use:

File path: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`

```python
class WorkflowCliToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    stdout: str
    stderr: str
    exit_code: int

class WorkflowCliToolFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 1
```

- [ ] **Step 3: Implement `make_workflow_cli_tool`**

Use `shlex.split(command)` to build argv. Capture stdout/stderr with `contextlib.redirect_stdout` and `redirect_stderr`. Call `await ergon_cli.main._main(argv)`.

Do not spawn a subprocess.

- [ ] **Step 4: Run wrapper tests**

Run:

```bash
pytest tests/unit/state/test_workflow_cli_tool.py -v
```

Expected: all tests pass.

## Task 4: Add a ResearchRubrics Workflow CLI ReAct Worker

**Files:**

- New worker: `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`
- Registry edit: `ergon_builtins/ergon_builtins/registry_data.py`
- Test: update `tests/unit/state/test_research_rubrics_workers.py` or add a focused worker wiring test beside it.

- [ ] **Step 1: Create the proof-of-concept worker**

Create `ResearchRubricsWorkflowCliReActWorker` as the first consumer of the workflow CLI tool.

Do not alter `ResearchRubricsResearcherWorker` for this proof of concept. Keeping the new behavior behind a separate worker slug makes it easy to compare workflow-CLI behavior against the existing research-rubrics agent.

- [ ] **Step 2: Add the workflow tool to the new worker**

File path: `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`

```python
class ResearchRubricsWorkflowCliReActWorker(ResearchRubricsResearcherWorker):
    """Research-rubrics ReAct worker with the workflow CLI tool enabled."""
```

Inside `execute()`, mirror the existing research-rubrics runtime tool composition and add:

```python
workflow_tool = make_workflow_cli_tool(context=context)
self.tools = [*rr_tools, *graph_tools, Tool(function=workflow_tool, takes_ctx=False)]
```

If pydantic-ai expects the callable directly rather than prewrapped `Tool`, mirror the existing toolkit pattern.

- [ ] **Step 3: Update system prompt**

Add a short instruction:

File path: `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`

```text
Use the `workflow` tool to inspect task topology and resources. Start with
`inspect task-tree`, `inspect task-workspace`, or
`inspect resource-list --scope input`. If a visible resource from another task
is useful, run `manage materialize-resource --resource-id ... --dry-run`
before importing it into your workspace. Use `--dry-run` before any graph
lifecycle `manage ...` mutation command.
```

- [ ] **Step 4: Register the new worker slug**

File path: `ergon_builtins/ergon_builtins/registry_data.py`

```python
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    ResearchRubricsWorkflowCliReActWorker,
)

WORKERS: dict[str, Callable[..., Worker]] = {
    "researchrubrics-researcher": ResearchRubricsResearcherWorker,
    "researchrubrics-workflow-cli-react": ResearchRubricsWorkflowCliReActWorker,
}
```

- [ ] **Step 5: Run worker wiring test**

Run:

```bash
pytest tests/unit/state/test_research_rubrics_workers.py -v
```

Expected:

- `researchrubrics-workflow-cli-react` is registered.
- `ResearchRubricsWorkflowCliReActWorker` exposes the `workflow` tool.
- The prompt recommends `inspect task-workspace`, `inspect resource-list --scope input`, `manage materialize-resource --dry-run`, and `--dry-run` before graph lifecycle `manage` commands.
- Existing `ResearchRubricsResearcherWorker` assertions remain unchanged and do not require `workflow`.

## Task 5: Add Contract Tests Around Input Resource Semantics

**Files:**

- Test: `tests/unit/runtime/test_workflow_input_resource_semantics.py`
- Optional later implementation: thread computed IDs into `PreparedTaskExecution.input_resource_ids`.

- [ ] **Step 1: Test the default policy**

Build a graph:

```text
d_root -> d_left
d_root -> d_right
d_left -> d_join
d_right -> d_join
l_1 -> l_2 -> l_3
```

Assert:

- `d_join` input resources are exactly latest resources from `d_left` and `d_right`.
- `l_3` input resources are exactly latest resources from `l_2`, not `l_1`.
- roots and singletons have empty input resources.

- [ ] **Step 2: Decide whether to wire sandbox inputs now**

If included in this implementation, add:

- `input_resource_ids` to `PreparedTaskExecution`
- computation in `TaskExecutionService.prepare`
- pass through `_setup_sandbox` in `execute_task.py`
- optional `WorkerContext.input_resource_ids`

If not included, keep the CLI/tool behavior independent and leave sandbox auto-materialization as the next implementation plan.

## Task 6: Add Real-LLM Acceptance Rollout

**Files:**

- Modify: `tests/real_llm/benchmarks/test_researchrubrics.py`

- [ ] **Step 1: Parameterize the rollout worker and sample limit**

Keep the existing defaults for the current research-rubrics rollout, but allow the final acceptance run to choose the workflow-CLI worker and five samples:

```python
model = os.environ.get("ERGON_REAL_LLM_MODEL", _DEFAULT_MODEL)
benchmark = os.environ.get("ERGON_REAL_LLM_BENCHMARK", "researchrubrics")
worker = os.environ.get("ERGON_REAL_LLM_WORKER", "researchrubrics-researcher")
evaluator = os.environ.get("ERGON_REAL_LLM_EVALUATOR", "research-rubric")
limit = os.environ.get("ERGON_REAL_LLM_LIMIT", "1")
```

Then pass `limit` into the CLI invocation instead of hard-coding `"1"`.

- [ ] **Step 2: Preserve rollout artifact capture**

Keep the existing artifact behavior: CLI stdout/stderr, table dumps, dashboard screenshots, manifest, and `report.md`. The final review should use these artifacts to inspect the agent's actual behavior rather than asserting a brittle exact tool-call sequence.

- [ ] **Step 3: Run the final acceptance rollout**

Run:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=5 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s
```

Expected:

- The real-LLM test reaches a terminal run status: `completed`, `failed`, or `cancelled`.
- The rollout artifacts are written under `tests/real_llm/.rollouts/<timestamp>-<run_id>/`.
- The manifest records `worker=researchrubrics-workflow-cli-react` and `limit=5`.
- The generated `report.md` plus dumped persistence rows provide enough evidence to inspect whether the agent invoked `workflow(...)`, which workflow commands it chose, whether it materialized any copied resources, and whether those commands helped it orient around task topology/resources.

This is the final acceptance criterion for the feature. Unit and focused integration tests remain the normal correctness gate; this rollout is the observational gate for whether the workflow CLI is useful to a real ResearchRubrics agent.

## Verification

Run focused tests:

```bash
pytest tests/unit/runtime/test_workflow_navigation_service.py tests/unit/runtime/test_workflow_resource_materialization_service.py tests/unit/cli/test_workflow_cli.py tests/unit/state/test_workflow_cli_tool.py -v
```

Run affected worker tests:

```bash
pytest tests/unit/state/test_research_rubrics_workers.py -v
```

If sandbox input threading is included, also run:

```bash
pytest tests/unit/runtime/test_workflow_input_resource_semantics.py -v
```

Final acceptance rollout:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=5 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s
```
