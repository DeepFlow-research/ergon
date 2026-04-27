# Finish Agent Workflow CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish `ergon workflow` as an agent-facing CLI for task editing and resource copying in one PR off `main`.

**Architecture:** Extend the already-merged V1 instead of replacing it. Keep scoped reads and mutation policy in `WorkflowService`, command parsing/rendering in `ergon_cli.commands.workflow`, and model-facing scope injection in `workflow_cli_tool`. All commands stay current-run/current-node scoped unless an injected manager-capable context explicitly permits broader graph edits.

**Tech Stack:** Python, argparse, SQLModel, existing `WorkflowGraphRepository`, existing run graph tables, pydantic DTOs, pytest.

---

## Current Baseline

Already merged:

- `ergon workflow ...` top-level command.
- `WorkflowService` with task/resource inspection and `materialize_resource`.
- `workflow(command)` pydantic-ai wrapper with injected run/node/execution/sandbox scope.
- ResearchRubrics workflow worker registration.

## Implementation Tasks

### Task 1: Real Task Editing Commands

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_service.py`
- Modify: `ergon_cli/ergon_cli/commands/workflow.py`
- Test: `tests/unit/runtime/test_workflow_service.py`
- Test: `tests/unit/cli/test_workflow_cli.py`

- [ ] Add a `WorkflowMutationRef` DTO with `action`, `dry_run`, `node`, `edge`, `message`, and `suggested_commands`.
- [ ] Add service methods for `add_task`, `add_edge`, `update_task_description`, `restart_task`, and `abandon_task`.
- [ ] Use `WorkflowGraphRepository` for graph writes and mutation logging.
- [ ] Keep `--dry-run` behavior identical to real command validation but without writes.
- [ ] Add CLI parser arguments for task slug, description, worker, source/target, and status fields.
- [ ] Add text and JSON renderers for mutation results.
- [ ] Verify with focused unit tests before moving on.

### Task 2: Resource Copying Completion

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_service.py`
- Modify: `ergon_cli/ergon_cli/commands/workflow.py`
- Test: `tests/unit/runtime/test_workflow_service.py`
- Test: `tests/unit/cli/test_workflow_cli.py`

- [ ] Add `inspect resource-location`.
- [ ] Add `inspect task-workspace`.
- [ ] Harden `materialize-resource` destination handling: reject absolute paths, `..`, and paths outside `/workspace`.
- [ ] Preserve source resource bytes and row unchanged.
- [ ] Ensure copied resource rows use `RunResourceKind.IMPORT`, `copied_from_resource_id`, and metadata with source resource, source task, and sandbox destination.
- [ ] Add JSON/text outputs for resource location and task workspace.
- [ ] Verify with unit tests and one integration-style sandbox-manager-injected test.

### Task 3: Agent Wrapper Permissions

**Files:**
- Modify: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Test: `tests/unit/state/test_workflow_cli_tool.py`

- [ ] Add a permission mode to the wrapper: leaf agents can inspect and materialize visible resources; manager-capable agents can use graph edit commands.
- [ ] Reject user-supplied scope/context flags before command execution.
- [ ] Reject multiline commands.
- [ ] Return structured, model-readable failure strings instead of leaking tracebacks.
- [ ] Verify wrapper tests for allowed inspect, allowed materialize, denied graph edit, and allowed manager graph edit.

### Task 4: Acceptance Coverage

**Files:**
- Modify: existing smoke fixture workers only as needed.
- Modify: existing E2E assertions only as needed.
- Test: focused unit tests plus existing smoke tests.

- [ ] Ensure one deterministic no-LLM smoke path calls `workflow("inspect task-tree")`.
- [ ] Ensure one deterministic no-LLM smoke path calls `workflow("inspect resource-list --scope input")`.
- [ ] Ensure one deterministic no-LLM smoke path dry-runs `manage materialize-resource`.
- [ ] Keep real-LLM rollout optional, using `researchrubrics-workflow-cli-react`.
- [ ] Run focused workflow tests, Python unit tests touched by runtime changes, frontend contract generation if schemas change, and CI-fast-compatible checks.

## Verification Commands

Run incrementally:

```bash
uv run pytest tests/unit/runtime/test_workflow_service.py -v
uv run pytest tests/unit/cli/test_workflow_cli.py -v
uv run pytest tests/unit/state/test_workflow_cli_tool.py -v
```

Before PR:

```bash
uv run pytest tests/unit/runtime/test_workflow_service.py tests/unit/cli/test_workflow_cli.py tests/unit/state/test_workflow_cli_tool.py -v
uv run pytest tests/unit/runtime tests/unit/cli tests/unit/state -q
pnpm --dir ergon-dashboard run typecheck
```

