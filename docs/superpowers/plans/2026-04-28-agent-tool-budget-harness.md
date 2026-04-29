# Agent Tool Budget Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple, reusable tool-budget harness that prevents agent rollouts from looping indefinitely by counting `workflow` tool calls separately from all other tool calls and returning explicit budget-exhausted messages when either limit is reached.

**Architecture:** Use Pydantic AI dependency injection. `ReActWorker` passes an optional deps object into `Agent.iter(...)`; tools that participate in the budget accept `RunContext[AgentToolBudgetDeps]` and call `ctx.deps.tool_budget.check(...)` before doing work. The budget system is generic and benchmark-agnostic: it knows only `workflow` vs `other`, not ResearchRubrics, Exa, or rubric-specific concepts. Reference: [Pydantic AI dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/).

**Tech Stack:** Python 3.13, pydantic-ai `RunContext`, Ergon `ReActWorker`, existing tool callables, pytest smoke checks, real-LLM rollout artifacts, Logfire.

---

## Design

The harness should enforce two counters per agent execution:

```python
workflow_tool_calls <= max_workflow_tool_calls
other_tool_calls <= max_other_tool_calls
```

Initial defaults:

```python
AgentToolBudgetPolicy(
    max_workflow_tool_calls=12,
    max_other_tool_calls=12,
    warning_at_remaining=3,
)
```

The budget does not decide which benchmark is running and does not know about Exa. It only sees:

- `workflow` calls: the workflow CLI tool.
- `other` calls: context-gathering and workspace-inspection tools other than `workflow`.
- `finalization` calls: tools that produce final output artifacts, such as report writing. These count for observability but are not blocked, because the budget should push the agent into finalization rather than prevent it.

When a limit is reached, the tool returns a normal structured tool result:

```python
AgentToolBudgetExhaustedResult(
    status="TOOL_BUDGET_EXHAUSTED",
    reason="workflow tool budget reached",
    message="Stop calling workflow. Use currently visible context/resources and produce the best possible final output.",
    budget_state={...},
)
```

or:

```python
AgentToolBudgetExhaustedResult(
    status="TOOL_BUDGET_EXHAUSTED",
    reason="non-workflow tool budget reached",
    message="Stop calling tools. Produce the final answer from the context already gathered.",
    budget_state={...},
)
```

This is intentionally not a Python exception. The model gets a final chance to converge. The outer `max_iterations` guard still raises a real error if the agent keeps looping after exhausted tool responses.

## Package Placement

- Generic budget state: `ergon_builtins/ergon_builtins/workers/baselines/tool_budget.py`
- Base agent execution hook: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Budgeted workflow command tool: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Budgeted non-workflow tools for this rollout: `ergon_builtins/ergon_builtins/tools/research_rubrics_toolkit.py` and `ergon_builtins/ergon_builtins/tools/graph_toolkit.py`
- Worker-specific budget policy wiring: `ergon_builtins/ergon_builtins/workers/research_rubrics/`
- Rollout diagnostics: `tests/real_llm/`

## Added Files

```text
ergon_builtins/
  ergon_builtins/
    workers/
      baselines/
        tool_budget.py
```

`tool_budget.py` owns the generic Pydantic models for budget policy, mutable per-execution budget state, deps passed into pydantic-ai, and helper logic for attaching warning text to tool results.

## Edited Files

```text
ergon_builtins/
  ergon_builtins/
    tools/
      graph_toolkit.py
      research_rubrics_toolkit.py
      workflow_cli_tool.py
    workers/
      baselines/
        react_worker.py
      research_rubrics/
        researcher_worker.py
        workflow_cli_react_worker.py

tests/
  real_llm/
    artifact_health.py
    rollout.py
```

Edit responsibilities:

- `react_worker.py`: add an optional deps hook, pass deps into `Agent.iter(...)`, and raise when `max_iterations` is hit.
- `workflow_cli_tool.py`: edit the existing workflow tool function path to support a ctx-taking budgeted mode for `workflow` calls.
- `research_rubrics_toolkit.py`: convert participating tools to ctx-taking functions and count context-gathering tools as `other`, while allowing report-writing as `finalization`.
- `graph_toolkit.py`: convert graph/resource tools to ctx-taking functions and count them as `other`.
- `researcher_worker.py`: provide generic budget deps to `ReActWorker` and steer the prompt toward quick convergence.
- `workflow_cli_react_worker.py`: provide generic budget deps, use budgeted workflow tool mode, and steer the prompt toward deliberate workflow use and subagent coordination.
- `artifact_health.py`: derive `workflow_tool_calls`, `other_tool_calls`, `budget_exhausted`, and `missing_final_report` from existing rollout artifacts.
- `rollout.py`: include those derived counters in `report.md`.

## Deleted Files

```text
(none)
```

## Optional Later Files

If other benchmarks start showing the same loop behavior, apply the same `RunContext[AgentToolBudgetDeps]` pattern to their toolkits:

```text
ergon_builtins/
  ergon_builtins/
    benchmarks/
      gdpeval/
        toolkit.py
      minif2f/
        toolkit.py
      swebench_verified/
        toolkit.py
```

---

## Task 1: Add Generic Tool Budget State

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/baselines/tool_budget.py`

- [ ] **Step 1: Create generic budget types**

Create `tool_budget.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ToolBudgetKind = Literal["workflow", "other", "finalization"]
ToolBudgetExhaustedStatus = Literal["TOOL_BUDGET_EXHAUSTED"]


class AgentToolBudgetExhaustedResult(BaseModel):
    status: ToolBudgetExhaustedStatus = "TOOL_BUDGET_EXHAUSTED"
    reason: str
    message: str
    budget_state: dict[str, Any]  # slopcop: ignore[no-typing-any]


class AgentToolBudgetPolicy(BaseModel):
    model_config = {"frozen": True}

    max_workflow_tool_calls: int = 12
    max_other_tool_calls: int = 12
    warning_at_remaining: int = 3


class AgentToolBudgetDecision(BaseModel):
    model_config = {"frozen": True}

    allowed: bool
    warning: str | None = None
    exhausted: AgentToolBudgetExhaustedResult | None = None


class AgentToolBudgetState(BaseModel):
    policy: AgentToolBudgetPolicy = Field(default_factory=AgentToolBudgetPolicy)
    workflow_tool_calls: int = 0
    other_tool_calls: int = 0
    finalization_tool_calls: int = 0
    calls_by_tool: dict[str, int] = Field(default_factory=dict)

    def check(self, tool_name: str, kind: ToolBudgetKind) -> AgentToolBudgetDecision:
        self.calls_by_tool[tool_name] = self.calls_by_tool.get(tool_name, 0) + 1

        if kind == "workflow":
            self.workflow_tool_calls += 1
            if self.workflow_tool_calls > self.policy.max_workflow_tool_calls:
                return AgentToolBudgetDecision(
                    allowed=False,
                    exhausted=self.exhausted_result("workflow tool budget reached"),
                )
            remaining = self.policy.max_workflow_tool_calls - self.workflow_tool_calls
        elif kind == "finalization":
            self.finalization_tool_calls += 1
            return AgentToolBudgetDecision(allowed=True)
        else:
            self.other_tool_calls += 1
            if self.other_tool_calls > self.policy.max_other_tool_calls:
                return AgentToolBudgetDecision(
                    allowed=False,
                    exhausted=self.exhausted_result("non-workflow tool budget reached"),
                )
            remaining = self.policy.max_other_tool_calls - self.other_tool_calls

        if remaining <= self.policy.warning_at_remaining:
            return AgentToolBudgetDecision(
                allowed=True,
                warning=(
                    f"TOOL_BUDGET_WARNING: {remaining} {kind} tool calls remain. "
                    "Converge now using the context already gathered."
                ),
            )
        return AgentToolBudgetDecision(allowed=True)

    def snapshot(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        return {
            "workflow_tool_calls": self.workflow_tool_calls,
            "max_workflow_tool_calls": self.policy.max_workflow_tool_calls,
            "other_tool_calls": self.other_tool_calls,
            "max_other_tool_calls": self.policy.max_other_tool_calls,
            "finalization_tool_calls": self.finalization_tool_calls,
            "calls_by_tool": dict(sorted(self.calls_by_tool.items())),
        }

    def exhausted_result(self, reason: str) -> AgentToolBudgetExhaustedResult:
        return AgentToolBudgetExhaustedResult(
            reason=reason,
            message=(
                "Stop calling tools in this category. Use the context/resources already "
                "available and produce the best possible final output. If the output is "
                "incomplete, state what context or resource was missing."
            ),
            budget_state=self.snapshot(),
        )


class AgentToolBudgetDeps(BaseModel):
    tool_budget: AgentToolBudgetState


def with_budget_warning(result: Any, warning: str | None) -> Any:  # slopcop: ignore[no-typing-any]
    if warning is None:
        return result
    if isinstance(result, str):
        return f"{result}\n\n{warning}"
    if isinstance(result, dict):
        updated = dict(result)
        updated["tool_budget_warning"] = warning
        return updated
    return result
```

- [ ] **Step 2: Run import smoke check**

Run:

```bash
uv run python - <<'PY'
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetPolicy,
    AgentToolBudgetState,
)

state = AgentToolBudgetState(
    policy=AgentToolBudgetPolicy(max_workflow_tool_calls=1, max_other_tool_calls=2),
)
deps = AgentToolBudgetDeps(tool_budget=state)
print(deps.tool_budget.check("workflow", "workflow").allowed)
print(deps.tool_budget.check("workflow", "workflow").allowed)
print(deps.tool_budget.snapshot())
PY
```

Expected: first line `True`, second line `False`, then a snapshot dictionary.

---

## Task 2: Pass Deps Through ReActWorker

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`

- [ ] **Step 1: Add a deps hook**

Add to `ReActWorker`:

```python
    def build_agent_deps(self, context: WorkerContext) -> Any | None:  # slopcop: ignore[no-typing-any]
        return None
```

- [ ] **Step 2: Pass context into `_run_agent`**

Change:

```python
async for turn in self._run_agent(task):
```

to:

```python
async for turn in self._run_agent(task, context):
```

Change `_run_agent` signature:

```python
    async def _run_agent(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
```

- [ ] **Step 3: Pass deps to pydantic-ai**

Before `Agent(...)`:

```python
        agent_deps = self.build_agent_deps(context)
        deps_type = type(agent_deps) if agent_deps is not None else None
```

Change the agent construction to include:

```python
            deps_type=deps_type,
```

Change `agent.iter(...)` to include:

```python
                deps=agent_deps,
```

- [ ] **Step 4: Make max-iteration exhaustion visible**

Replace the current `break` on `max_iterations` with:

```python
                        for turn in adapter.build_new_turns(
                            run.ctx.state.message_history,
                            cursor,
                            flush_pending=True,
                        ):
                            yield turn
                        raise RuntimeError(
                            f"ReActWorker exceeded max_iterations={self.max_iterations}"
                        )
```

- [ ] **Step 5: Run existing focused tests**

Run:

```bash
uv run pytest tests/unit/workers/test_react_worker_contract.py tests/unit/builtins/common/test_transcript_adapters.py -q
```

Expected: PASS.

---

## Task 3: Budget the Workflow Tool

**Files:**
- Modify: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Existing test: `tests/unit/state/test_workflow_cli_tool.py`

- [ ] **Step 1: Add ctx-aware mode**

Import:

```python
from pydantic_ai import RunContext
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetExhaustedResult,
    with_budget_warning,
)
```

Add parameter to `make_workflow_cli_tool`:

```python
    budgeted: bool = False,
```

Edit the existing function body directly. Do not add a separate wrapper around workflow execution. Because pydantic-ai needs a clear callable signature, use two function definitions inside `make_workflow_cli_tool`: one ctx-taking definition for `budgeted=True`, and the existing no-ctx definition for `budgeted=False`.

```python
    if budgeted:
        async def workflow(
            ctx: RunContext[AgentToolBudgetDeps],
            command: str,
        ) -> str | AgentToolBudgetExhaustedResult:
            decision = ctx.deps.tool_budget.check("workflow", "workflow")
            if not decision.allowed:
                assert decision.exhausted is not None
                return decision.exhausted

            if worker_context.node_id is None:
                raise ValueError("workflow tool requires WorkerContext.node_id")

            output = await asyncio.to_thread(
                execute_command,
                command,
                context=WorkflowCommandContext(
                    run_id=worker_context.run_id,
                    node_id=worker_context.node_id,
                    execution_id=worker_context.execution_id,
                    sandbox_task_key=sandbox_task_key,
                    benchmark_type=benchmark_type,
                ),
                session_factory=session_factory,
                service=service_factory(),
            )
            if output.exit_code != 0:
                detail = output.stderr or output.stdout
                result = f"workflow exited {output.exit_code}: {detail}".strip()
            elif output.stderr:
                result = f"{output.stdout}\n\nstderr:\n{output.stderr}".strip()
            else:
                result = output.stdout
            return with_budget_warning(result, decision.warning)

        return workflow
```

Keep the existing no-ctx `workflow(command: str)` function as the `budgeted=False` branch:

```python
    async def workflow(command: str) -> str:
        if worker_context.node_id is None:
            raise ValueError("workflow tool requires WorkerContext.node_id")

        output = await asyncio.to_thread(
            execute_command,
            command,
            context=WorkflowCommandContext(
                run_id=worker_context.run_id,
                node_id=worker_context.node_id,
                execution_id=worker_context.execution_id,
                sandbox_task_key=sandbox_task_key,
                benchmark_type=benchmark_type,
            ),
            session_factory=session_factory,
            service=service_factory(),
        )
        if output.exit_code != 0:
            detail = output.stderr or output.stdout
            return f"workflow exited {output.exit_code}: {detail}".strip()
        if output.stderr:
            return f"{output.stdout}\n\nstderr:\n{output.stderr}".strip()
        return output.stdout

    return workflow
```

- [ ] **Step 2: Preserve existing behavior**

Run:

```bash
uv run pytest tests/unit/state/test_workflow_cli_tool.py -q
```

Expected: PASS. Existing tests use `budgeted=False`.

---

## Task 4: Budget Other Tools Used by This Harness

**Files:**
- Modify: `ergon_builtins/ergon_builtins/tools/research_rubrics_toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/tools/graph_toolkit.py`

- [ ] **Step 1: Convert ResearchRubrics tools to ctx-taking functions**

In `research_rubrics_toolkit.py`, import:

```python
from pydantic_ai import RunContext
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetExhaustedResult,
    with_budget_warning,
)
```

For each tool function, add `ctx` as the first arg:

```python
ctx: RunContext[AgentToolBudgetDeps],
```

At the top of each context-gathering tool:

```python
decision = ctx.deps.tool_budget.check("<actual_tool_name>", "other")
if not decision.allowed:
    assert decision.exhausted is not None
    return decision.exhausted
```

For final-output tools such as `write_report_draft` and `edit_report_draft`, use:

```python
decision = ctx.deps.tool_budget.check("<actual_tool_name>", "finalization")
```

Do not block finalization tools after `other` is exhausted. The budget exists to force convergence into these tools.

Use the actual function/tool name for each function so `calls_by_tool` remains useful in artifacts.

After the existing result is produced:

```python
return cast(<ResponseType> | AgentToolBudgetExhaustedResult, with_budget_warning(resp, decision.warning))
```

For response types that are Pydantic models, returning `AgentToolBudgetExhaustedResult` on exhaustion is acceptable because the tool result is serialized back to the model. Keep type annotations broad enough, for example:

```python
) -> SearchResponse | AgentToolBudgetExhaustedResult:
```

Change each `Tool(..., takes_ctx=False)` to:

```python
Tool(function=..., takes_ctx=True)
```

- [ ] **Step 2: Convert graph/resource tools to ctx-taking functions**

In `graph_toolkit.py`, apply the same pattern:

```python
decision = ctx.deps.tool_budget.check("list_child_resources", "other")
if not decision.allowed:
    assert decision.exhausted is not None
    return decision.exhausted
```

Update all graph tools to `takes_ctx=True`.

- [ ] **Step 3: Run import smoke checks**

Run:

```bash
uv run python - <<'PY'
from ergon_builtins.tools.research_rubrics_toolkit import ResearchRubricsToolkit
from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
print(ResearchRubricsToolkit)
print(ResearchGraphToolkit)
PY
```

Expected: imports cleanly.

---

## Task 5: Wire Budget Deps Into Current ResearchRubrics Workers

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py`

- [ ] **Step 1: Add policy imports**

In both workers:

```python
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetPolicy,
    AgentToolBudgetState,
)
```

- [ ] **Step 2: Add a shared policy**

Use the same generic policy in both files:

```python
_TOOL_BUDGET_POLICY = AgentToolBudgetPolicy(
    max_workflow_tool_calls=12,
    max_other_tool_calls=12,
    warning_at_remaining=3,
)
```

- [ ] **Step 3: Create deps per execution**

In each `execute(...)`, before calling `super().execute(...)`:

```python
self._agent_deps = AgentToolBudgetDeps(
    AgentToolBudgetState(_TOOL_BUDGET_POLICY),
)
```

Add method:

```python
def build_agent_deps(self, context: WorkerContext) -> AgentToolBudgetDeps:
    return self._agent_deps
```

These worker instances are currently execution-scoped. If that changes later, move deps creation into a base-class execution context instead of storing on `self`.

- [ ] **Step 4: Use budgeted workflow tool in manager**

In `workflow_cli_react_worker.py`, change:

```python
workflow_tool = make_workflow_cli_tool(...)
```

to:

```python
workflow_tool = make_workflow_cli_tool(..., budgeted=True)
```

- [ ] **Step 5: Tighten prompts, but keep them generic**

Researcher prompt:

```text
You have a limited non-workflow tool budget. Gather enough context, then stop using tools and write final_output/report.md. If any tool returns TOOL_BUDGET_WARNING or TOOL_BUDGET_EXHAUSTED, immediately produce the best possible final report from the context already gathered.
```

Manager prompt:

```text
For multi-step work, divide and conquer with focused subagents to manage context. Workflow calls are limited, so inspect deliberately, create focused children, avoid duplicate research, and converge after child resources are visible. If any tool returns TOOL_BUDGET_WARNING or TOOL_BUDGET_EXHAUSTED, stop polling/searching and produce the best possible final output from current context/resources.
```

- [ ] **Step 6: Run focused worker import**

Run:

```bash
uv run python - <<'PY'
from ergon_builtins.workers.research_rubrics.researcher_worker import ResearchRubricsResearcherWorker
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import ResearchRubricsWorkflowCliReActWorker
print(ResearchRubricsResearcherWorker.type_slug)
print(ResearchRubricsWorkflowCliReActWorker.type_slug)
PY
```

Expected: prints both type slugs.

---

## Task 6: Add Lightweight Rollout Reporting

**Files:**
- Modify: `tests/real_llm/artifact_health.py`
- Modify: `tests/real_llm/rollout.py`

- [ ] **Step 1: Count budget signals from existing events**

In `artifact_health.py`, derive:

```python
workflow_tool_calls
other_tool_calls
budget_exhausted
missing_final_report
```

Implementation rule:

- If `tool_name == "workflow"`, increment `workflow_tool_calls`.
- Else if event type is `tool_call`, increment `other_tool_calls`.
- If any event payload has `status == "TOOL_BUDGET_EXHAUSTED"`, set `budget_exhausted=True`.
- If no resource path is `final_output/report.md`, set `missing_final_report=True`.

- [ ] **Step 2: Show counters in rollout report**

In `rollout.py`, add lines:

```python
f"- workflow tool calls: {health.workflow_tool_calls}",
f"- other tool calls: {health.other_tool_calls}",
f"- budget exhausted: {health.budget_exhausted}",
f"- missing final report: {health.missing_final_report}",
```

- [ ] **Step 3: Run collection smoke**

Run:

```bash
uv run pytest tests/real_llm -q --collect-only
```

Expected: collection succeeds.

---

## Task 7: Verify With One Real Sample

**Files:**
- No new source files.

- [ ] **Step 1: Run focused checks**

Run:

```bash
uv run pytest \
  tests/unit/state/test_workflow_cli_tool.py \
  tests/unit/workers/test_react_worker_contract.py \
  tests/unit/builtins/common/test_transcript_adapters.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run lint on changed files**

Run:

```bash
uv run ruff check \
  ergon_builtins/ergon_builtins/workers/baselines/tool_budget.py \
  ergon_builtins/ergon_builtins/workers/baselines/react_worker.py \
  ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py \
  ergon_builtins/ergon_builtins/tools/research_rubrics_toolkit.py \
  ergon_builtins/ergon_builtins/tools/graph_toolkit.py \
  ergon_builtins/ergon_builtins/workers/research_rubrics/researcher_worker.py \
  ergon_builtins/ergon_builtins/workers/research_rubrics/workflow_cli_react_worker.py \
  tests/real_llm/artifact_health.py \
  tests/real_llm/rollout.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Rebuild and run one sample**

Run:

```bash
POSTGRES_PASSWORD=ergon_dev \
TEST_HARNESS_SECRET=real-llm-secret \
ENABLE_TEST_HARNESS=1 \
ENABLE_SMOKE_FIXTURES=0 \
ERGON_STARTUP_PLUGINS= \
ERGON_LOGFIRE_PYDANTIC_AI=1 \
ERGON_LOGFIRE_SERVICE_NAME=ergon-builtins \
ERGON_LOGFIRE_ENVIRONMENT=real-llm \
docker compose build api
```

Then:

```bash
POSTGRES_PASSWORD=ergon_dev \
TEST_HARNESS_SECRET=real-llm-secret \
ENABLE_TEST_HARNESS=1 \
ENABLE_SMOKE_FIXTURES=0 \
ERGON_STARTUP_PLUGINS= \
ERGON_LOGFIRE_PYDANTIC_AI=1 \
ERGON_LOGFIRE_SERVICE_NAME=ergon-builtins \
ERGON_LOGFIRE_ENVIRONMENT=real-llm \
docker compose up -d --no-build --force-recreate --wait api
```

Then:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=1 \
ERGON_REAL_LLM_BUDGET_USD=5 \
TEST_HARNESS_SECRET=real-llm-secret \
ENABLE_TEST_HARNESS=1 \
ENABLE_SMOKE_FIXTURES=0 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -q -s --assume-stack-up
```

Expected improvement:

- no silent runaway loop.
- report shows `workflow tool calls <= 12`, or budget exhaustion is visible.
- report shows `other tool calls <= 12`, or budget exhaustion is visible.
- if the run fails, it fails with persisted transcript/error context that explains whether the budget was exhausted.

---

## Notes

- This is intentionally simpler than per-tool caps. No Exa-specific budget, no rubric-specific budget, no child-poll-specific budget.
- This still supports better prompt steering, but prompt steering is advisory. The two counters are enforcement.
- We should not add broad unit tests for every tool. Existing workflow tests, import smoke checks, lint, and the one-sample real rollout are enough for this change.
- Do not commit unless explicitly asked.
