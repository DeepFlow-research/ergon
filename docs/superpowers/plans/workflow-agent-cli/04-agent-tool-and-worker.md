# 04 — Agent Tool and Worker POC

## Agent Invocation Model

The agent runs locally in the worker process. The environment runs in E2B. Therefore `workflow(...)` should read local Postgres directly, then use existing sandbox manager APIs for approved workspace materialization.

Do not put this command inside the E2B sandbox.

## Tool Factory

Create `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`.

```python
def make_workflow_cli_tool(
    *,
    context: WorkerContext,
    allowed_scopes: frozenset[str] = frozenset({"input", "own", "upstream", "children", "descendants", "visible"}),
    manager_capable: bool = False,
) -> Callable[..., Awaitable[WorkflowCliToolResponse]]:
    ...
```

Tool signature:

```python
async def workflow(command: str, timeout_s: int = 10) -> WorkflowCliToolResponse:
    """Run a scoped workflow navigation command."""
```

Examples the prompt can show:

```text
inspect task-tree
inspect task-workspace
inspect resource-list --scope input
inspect resource-list --scope visible --limit 20
inspect resource-content --resource-id ...
manage materialize-resource --resource-id ... --dry-run
manage restart-task --task-slug l_2 --dry-run
```

## Wrapper Rules

The wrapper:

- receives only the model's subcommand string
- prepends `workflow`
- injects `--run-id <context.run_id>`
- injects `--node-id <context.node_id>`
- injects `--execution-id <context.execution_id>` when supported
- injects `--sandbox-id <context.sandbox_id>` when supported
- injects `--sandbox-task-key <context.task_id or context.node_id>` when supported
- rejects user-supplied `--run-id`, `--node-id`, `--execution-id`, `--sandbox-id`, `--sandbox-task-key`, `--definition-id`, `--experiment-id`, or `--cohort-id`
- calls `ergon_cli.main._main(argv)` in-process with stdout/stderr captured
- rejects multiline input and unrelated top-level commands

## Permissions

All workflow CLI commands are current-run scoped by invariant. Cross-run output is a CLI bug.

Leaf agents:

- can inspect `input`, `own`, `upstream`, `children`, `descendants`, and capped `visible` resources when allowed by profile
- can run `manage materialize-resource` for visible current-run resources
- cannot run graph lifecycle mutations

Manager-capable agents:

- can inspect the same scopes
- can run `manage materialize-resource`
- can run graph lifecycle commands: `create-task`, `create-task-plan`, `create-dependency`, `restart-task`, `abandon-task`, `update-task-description`

No command queries eval tables or accepts raw SQL.

## Prompt Guidance

Use this instruction in the POC worker:

```text
Use the `workflow` tool to inspect task topology and resources. Start with
`inspect task-tree`, `inspect task-workspace`, or
`inspect resource-list --scope input`. If a visible resource from another task
is useful, run `manage materialize-resource --resource-id ... --dry-run`
before importing it into your workspace. Use `--dry-run` before any graph
lifecycle `manage ...` mutation command.
```

## POC Worker

Create:

```text
ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py
```

Class:

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

## Registry

Modify `ergon_builtins/ergon_builtins/registry_data.py`:

```python
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    ResearchRubricsWorkflowCliReActWorker,
)

WORKERS: dict[str, Callable[..., Worker]] = {
    "researchrubrics-researcher": ResearchRubricsResearcherWorker,
    "researchrubrics-workflow-cli-react": ResearchRubricsWorkflowCliReActWorker,
}
```

Do not alter the existing `"researchrubrics-researcher"` worker behavior for this POC.
