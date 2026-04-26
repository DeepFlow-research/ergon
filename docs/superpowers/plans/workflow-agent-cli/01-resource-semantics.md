# 01 — Resource Semantics

## Core Rule

Resources are immutable published artifacts. A task may read a visible resource from another task in the same run, including a resource from a divergent branch of the control DAG, but it must never mutate the source row or source bytes.

The workflow CLI treats copying as a fork:

- **Read is context.** `inspect resource-content` does not change graph state.
- **Materialize is fork.** Copying a resource into the current agent workspace creates a new `RunResource` row owned by the current task execution.
- **Publish is ownership.** If the current task edits the copied file and publishes it later, the edited artifact is another new resource owned by the current task execution.
- **Lineage is evidence.** The copied resource row records `copied_from_resource_id=<source_resource_id>`.
- **Control edges schedule work; resource lineage explains information flow.** Materializing a resource from a divergent DAG branch must not add a control dependency edge.

## Current-Run Invariant

All workflow CLI commands are current-run scoped by invariant. The agent wrapper injects `run_id`; the model cannot select a run.

`visible` is not a cross-run permission mode. It is the broadest resource discovery scope **inside the injected current run**. It exists so agents can find useful resources from divergent DAG branches. Any cross-run result is a correctness/security bug.

## Copy Example

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

## Materialization Ordering

`workflow manage materialize-resource` must:

1. Resolve the source resource by ID inside the injected current run.
2. Validate visibility and destination before side effects.
3. Write bytes to the sandbox destination.
4. Append the copied `RunResource` row only after the sandbox write succeeds.
5. Update `/workspace/.ergon/resource_imports.json` after the copied row exists.

If the manifest update fails after the file copy/resource row succeeds, return a structured warning rather than pretending the source was not materialized.

## Naming

Default copied names should make ownership clear:

```text
paper.pdf -> paper (copy).pdf
paper (copy).pdf -> paper (copy 2).pdf
```

Identity comes from `resource_id` and `content_hash`, not names. The name suffix is for human and agent readability.

## V1 Lineage Boundary

V1 adds a nullable self-reference on `RunResource`: `copied_from_resource_id`.

That is enough for one-resource materialization. Do not build a many-to-many lineage table in v1. If synthesis from multiple copied resources becomes central, add `run_resource_lineage` later.

For arbitrary later edits, it is enough in v1 that the run has:

- the copied `RunResource` row
- `copied_from_resource_id`
- the import manifest
- tool-call context events

Do not pretend to infer every arbitrary transformation automatically.
