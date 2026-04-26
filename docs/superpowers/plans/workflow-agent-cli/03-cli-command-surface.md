# 03 — CLI Command Surface

## Global Rules

Build two command groups:

- `workflow inspect ...`: read-only task topology, dependency, resource, and workspace inspection.
- `workflow manage ...`: state-changing commands. Graph lifecycle commands require a manager-capable profile; `materialize-resource` is available to task agents for visible resources.

Every command is scoped by injected runtime context:

- `run_id`
- `node_id`
- `execution_id` when needed
- `sandbox_id` / `sandbox_task_key` when materializing

All commands support `--format text|json` and `--explain`. Commands that can produce large output support `--limit`, `--max-chars`, or `--max-bytes`.

All `manage ...` commands support `--dry-run`.

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

### `workflow inspect task-tree`

Shows a recursive task subtree, grouped by level. This is the default orientation command for agents.

Examples:

```bash
workflow("inspect task-tree")
workflow("inspect task-tree --from current --depth 2")
workflow("inspect task-tree --from root --depth 3")
workflow("inspect task-tree --from d_root --level 2")
workflow("inspect task-tree --from d_root --status pending")
```

### `workflow inspect task-details`

Shows one task node plus latest execution summary.

Examples:

```bash
workflow("inspect task-details")
workflow("inspect task-details --task-slug d_left --include-output")
workflow("inspect task-details --task-slug d_left --format json")
```

### `workflow inspect task-dependencies`

Shows graph dependencies for a task.

Examples:

```bash
workflow("inspect task-dependencies")
workflow("inspect task-dependencies --task-slug d_join --direction upstream")
workflow("inspect task-dependencies --task-slug d_left --direction downstream --format json")
```

### `workflow inspect task-blockers`

Explains why a task is not ready, not completed, or cannot proceed.

Examples:

```bash
workflow("inspect task-blockers")
workflow("inspect task-blockers --task-slug d_join")
workflow("inspect task-blockers --task-slug l_3 --format json")
```

### `workflow inspect next-actions`

Gives a concise recovery/orientation summary.

Examples:

```bash
workflow("inspect next-actions")
workflow("inspect next-actions --include-completed")
```

### `workflow inspect resource-list`

Lists current-run resources visible under the selected scope.

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

- `input`: latest successful resources from immediate upstream dependency nodes.
- `upstream`: alias for `input` in v1.
- `own`: resources produced by the current node's latest execution.
- `children`: resources produced by direct child task executions.
- `descendants`: resources produced by descendants up to `--max-depth`.
- `visible`: broadest current-run discovery scope for resources the profile may see, including divergent DAG branches. This is not cross-run access.

### `workflow inspect resource-content`

Reads resource content from `RunResource.file_path`.

Examples:

```bash
workflow("inspect resource-content --resource-id $RESOURCE_ID")
workflow("inspect resource-content --resource-id $RESOURCE_ID --max-bytes 20000")
```

### `workflow inspect resource-location`

Returns resource metadata and local blob path without dumping content.

```bash
workflow("inspect resource-location --resource-id $RESOURCE_ID")
```

### `workflow inspect task-workspace`

Shows a compact current task workspace snapshot: task, execution, upstream dependencies, downstream dependents, input resources, own resources, children, and next commands.

```bash
workflow("inspect task-workspace")
workflow("inspect task-workspace --task-slug d_join")
workflow("inspect task-workspace --task-slug d_join --include-output")
```

## Manage Commands

### `workflow manage create-task`

Adds one dynamic subtask under the current node via `TaskManagementService.add_subtask`.

```bash
workflow("manage create-task --task-slug summarize_left --worker researchrubrics-smoke-leaf --description 'Summarize left branch'")
workflow("manage create-task --task-slug join --worker researchrubrics-smoke-leaf --description 'Join summaries' --depends-on summarize_left --dry-run")
```

### `workflow manage create-task-plan`

Adds multiple dynamic subtasks in one transaction via `TaskManagementService.plan_subtasks`.

```bash
workflow("manage create-task-plan --json '[{\"task_slug\":\"a\",\"description\":\"Do A\",\"assigned_worker_slug\":\"researchrubrics-smoke-leaf\"}]' --dry-run")
```

### `workflow manage create-dependency`

Adds a dependency edge between two existing visible tasks.

```bash
workflow("manage create-dependency --source summarize_left --target join --dry-run")
```

### `workflow manage restart-task`

Resets a terminal task back to pending via `TaskManagementService.restart_task`.

```bash
workflow("manage restart-task --task-slug l_2 --dry-run")
```

### `workflow manage abandon-task`

Cancels a task via `TaskManagementService.cancel_task`.

```bash
workflow("manage abandon-task --task-slug l_3 --dry-run")
```

### `workflow manage update-task-description`

Updates a non-running task description via `TaskManagementService.refine_task`.

```bash
workflow("manage update-task-description --task-slug l_3 --description 'Retry with corrected input file' --dry-run")
```

### `workflow manage materialize-resource`

Copies one immutable visible `RunResource` into the current agent's E2B workspace and records the copy as a new current-task-owned resource.

```bash
workflow("manage materialize-resource --resource-id $RESOURCE_ID")
workflow("manage materialize-resource --resource-id $RESOURCE_ID --destination imported/task-a/paper.pdf")
workflow("manage materialize-resource --resource-id $RESOURCE_ID --destination imported/task-a/paper.pdf --dry-run")
```

Text output:

```text
materialized resource
  source: res_a paper.pdf sha256:abc...
  copy:   res_b paper (copy).pdf kind=import
  copied_from_resource_id: res_a
  sandbox_path: /workspace/imported/task-a/paper (copy).pdf
  note: source resource was not modified
```

JSON output:

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

- `workflow messages send`
- `workflow manage remove-dependency`
- many-to-many resource lineage management
