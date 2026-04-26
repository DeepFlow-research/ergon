# 00 — Program, Scope, File Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ergon workflow ...`, an agent-local command surface for benchmark-task workers to inspect workflow topology/resources and explicitly materialize useful visible resources into their workspace without exposing raw SQL.

**Architecture:** Put scoped Postgres reads and resource materialization policy in one core workflow service, command parsing in `ergon_cli`, and the agent-callable wrapper in `ergon_builtins/tools`. The command runs in the local worker/API process, reads local Postgres via `get_session()`, and uses the existing sandbox manager to copy approved resources into the current E2B workspace.

**Tech Stack:** Python, argparse, SQLModel, Alembic migrations, pydantic-ai `Tool`, pytest, existing sandbox manager APIs.

---

## Package Placement

- Core workflow logic: `ergon_core/ergon_core/core/runtime/services/workflow_service.py`
- DTOs: `ergon_core/ergon_core/core/runtime/services/workflow_dto.py`
- CLI handlers: `ergon_cli/ergon_cli/commands/workflow.py`
- CLI registration: `ergon_cli/ergon_cli/main.py`
- Agent wrapper: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Proof-of-concept worker: `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`

Keep `ergon_builtins/ergon_builtins/tools/graph_toolkit.py` intact. `workflow` is the more general command-shaped interface; the existing graph toolkit remains a research-specific resource discovery toolkit.

## Added Files

```text
ergon_core/
  migrations/
    versions/
      <revision>_add_copied_from_resource_id.py
  ergon_core/
    core/
      runtime/
        services/
          workflow_dto.py
          workflow_service.py

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
      test_workflow_service.py
      test_workflow_input_resource_semantics.py
    cli/
      test_workflow_cli.py
    state/
      test_workflow_cli_tool.py
  integration/
    runtime/
      test_workflow_cli_materialize_resource.py
```

## Edited Files

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
  e2e/
    _asserts.py
    test_researchrubrics_smoke.py
    test_minif2f_smoke.py
    test_swebench_smoke.py
  real_llm/
    benchmarks/
      test_researchrubrics.py
```

`ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py` is intentionally not edited for the POC path.

## Deleted Files

```text
(none)
```

## Optional Later Files

Automatic input materialization at sandbox creation time is separate from `workflow manage materialize-resource`.

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

## Non-Goals

- Do not expose raw SQL.
- Do not expose resources from outside the injected current run. If that happens, it is a CLI bug.
- Do not expose eval/private/system data.
- Do not mutate source resources.
- Do not add E2B-side CLI execution or require E2B-to-localhost networking.
- Do not modify dashboard UI in v1, except optional future display of resource lineage.
