# PR 10b — ResearchRubrics Vertical

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ResearchRubrics tasks construct object-bound `Task` with
`ResearchE2BSandbox` and a serializable researcher worker.

**Architecture:** Repeat the MiniF2F + SWEBench vertical pattern for
ResearchRubrics. Imports the shared `ManagerBackedSandboxRuntime`
adapter PR 10a created. Adds one wrinkle: the rubric carries a
`JudgeCriterion` whose `judge_model` field must persist, so the
criterion itself becomes a Pydantic subclass.

**Tech Stack:** Builtin benchmark modules, sandbox adapters, Pydantic
worker config, pytest.

PR 10a and PR 10b have no sequential dependency; either can land first.
PR 10c's cleanup is the only place ordering matters.

---

## Common Conversion Recipe

See [`11-pr-10a-swebench.md`](11-pr-10a-swebench.md) § Common
Conversion Recipe. The 8-step template is identical for every
vertical; this PR adds one extra step (re-home judge criterion).

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/sandboxes/research_e2b.py
ergon_builtins/ergon_builtins/toolkits/research_rubrics.py
ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/criteria.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py
ergon_cli/ergon_cli/commands/_registry.py        # add the slug factory
```

## Task 1: Add `ResearchE2BSandbox`

- [ ] **Step 1: Create the subclass**

`ergon_builtins/ergon_builtins/sandboxes/research_e2b.py`:

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import (
    ResearchRubricsSandboxManager,
)
from ergon_builtins.sandboxes._manager_backed import (
    ManagerBackedSandboxRuntime,
)


class ResearchE2BSandbox(Sandbox):
    template_id: str = "ergon-research-v1"
    requires_network: bool = True
    research_data_dir: str = "/workspace/research_data"

    async def provision(self) -> None:
        manager = ResearchRubricsSandboxManager(template_id=self.template_id)
        sandbox = await manager.create(task_id=uuid4(), envs=self.env)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )

    async def _bind_runtime(self, sandbox_id: str) -> None:
        # Eval-side attach: reconnect to an already-running sandbox so
        # evaluate_task_run can call task.sandbox.run_command(...) on the
        # same external sandbox worker_execute provisioned.
        manager = ResearchRubricsSandboxManager(template_id=self.template_id)
        sandbox = await manager.connect(sandbox_id=sandbox_id)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )
```

If `ResearchRubricsSandboxManager` lacks `connect(sandbox_id=...)`,
add it at the manager layer — the synchronous-fanout eval path
requires reconnect-by-id on every builtin sandbox.

The shared `ManagerBackedSandboxRuntime` is the one PR 10a landed at
`ergon_builtins/sandboxes/_manager_backed.py`. If PR 10b lands first
(rather than after 10a), create the adapter as Step 0 — see PR 10a's
Task 1 Step 1 for the exact body.

## Task 2: Move Toolkit Helpers

- [ ] **Step 1: Move toolkit types**

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/researchrubrics/toolkit_types.py \
       ergon_builtins/ergon_builtins/toolkits/research_rubrics.py
```

- [ ] **Step 2: Convert to Pydantic**

Replace any dataclasses / namedtuples with a Pydantic BaseModel:

```python
from pydantic import BaseModel, ConfigDict


class ResearchRubricsToolkit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    judge_model: str = "openai:gpt-4o"
    max_search_calls: int = 12
    enable_web_browse: bool = True

    def tools(self, sandbox, task):
        from ergon_builtins.toolkits._research_tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move runtime tool construction into `_research_tools.py`; the toolkit
holds config only.

- [ ] **Step 3: Update importers**

```bash
rg "from ergon_builtins.benchmarks.researchrubrics.toolkit_types import" \
  ergon_builtins ergon_core
```

Replace with `from ergon_builtins.toolkits.research_rubrics import ResearchRubricsToolkit`.

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry call with constructor**

In `researchrubrics/worker_factory.py`:

```python
from ergon_builtins.toolkits.research_rubrics import ResearchRubricsToolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker


def make_research_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 16,
) -> ReActWorker:
    return ReActWorker(
        name="research-runner",
        model=model,
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=ResearchRubricsToolkit(),
    )
```

## Task 4: Re-Home Judge Criterion (Pydantic conversion)

ResearchRubrics rubrics carry a `JudgeCriterion` that today uses the
registry to look up its judge model. After PR 10b, the rubric must
persist alongside the worker config — the judge model field flows
through `_type`-discriminated JSON.

**Files:**

- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py`

- [ ] **Step 1: Convert `JudgeCriterion` to a Pydantic `Criterion` subclass**

```python
from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.rubric.evaluator import CriterionResult
from ergon_core.api.worker.results import WorkerOutput


class JudgeCriterion(Criterion):
    """LLM-judge criterion that scores worker_output against a rubric."""

    judge_model: str = "openai:gpt-4o"
    rubric_text: str

    async def evaluate(
        self,
        task: Task,
        worker_output: WorkerOutput,
    ) -> CriterionResult:
        # Per 01-api-surface.md, Criterion.evaluate takes
        # (task, worker_output) — the sandbox lives on task.sandbox.
        ...
```

`judge_model` and `rubric_text` are persistent fields — they round-trip
through `_type` JSON. The body of `evaluate` calls the judge model with
`task.description`, `worker_output.final_text`, and the rubric text.

## Task 5: Convert Benchmark Tasks

- [ ] **Step 1: Replace imports**

In `researchrubrics/benchmark.py`:

```python
# Delete:
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec

# Add:
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.sandboxes.research_e2b import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.worker_factory import (
    make_research_worker,
)
from ergon_builtins.benchmarks.researchrubrics.rubric import (
    make_research_rubric_for_instance,
)
```

- [ ] **Step 2: Replace `TaskSpec` construction**

Per-instance task becomes:

```python
Task[ResearchRubricsTaskPayload](
    task_slug="research-rubric",
    instance_key=instance.instance_id,
    description=instance.prompt,
    task_payload=ResearchRubricsTaskPayload(
        instance_id=instance.instance_id,
        question=instance.prompt,
        ground_truth_rubric=instance.rubric,
    ),
    worker=make_research_worker(),
    sandbox=ResearchE2BSandbox(),
    evaluators=(make_research_rubric_for_instance(instance),),
)
```

## Task 6: Add CLI Factory Entry

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/_registry.py`

- [ ] **Step 1: Register the ResearchRubrics experiment factory**

Following PR 8's dict-extension pattern:

```python
from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)


def _researchrubrics() -> Experiment:
    return Experiment(
        benchmark=ResearchRubricsBenchmark(),
        name="researchrubrics",
        description="Research Rubrics benchmark with LLM judge.",
        metadata={"source": "builtins"},
    )


BUILTIN_EXPERIMENT_FACTORIES["researchrubrics"] = _researchrubrics
```

## Task 7: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py`:

```python
import pytest
from ergon_core.api import Experiment
from ergon_core.core.application.experiments.definition_writer import (
    persist_definition,
)
from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)


@pytest.mark.asyncio
async def test_research_rubrics_persists_object_bound_task_json(session_factory):
    benchmark = ResearchRubricsBenchmark(limit=1)
    experiment = Experiment(
        benchmark=benchmark,
        name="research-smoke",
        metadata={"created_by": "test"},
    )

    handle = persist_definition(experiment)
    with session_factory() as session:
        rows = session.exec(
            "SELECT task_json FROM experiment_definition_tasks "
            "WHERE definition_id = :d",
            {"d": handle.definition_id},
        ).all()
    assert rows
    task_json = rows[0][0]
    assert task_json["sandbox"]["_type"].endswith(":ResearchE2BSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(
        ev.get("_type") for ev in task_json["evaluators"]
    ), "every evaluator entry must carry a `_type` discriminator"
    assert task_json["evaluators"][0]["_type"].endswith(":Rubric")
```

- [ ] **Step 2: Judge model round-trips**

```python
def test_research_rubric_judge_model_is_persisted():
    benchmark = ResearchRubricsBenchmark(limit=1)
    task = next(iter(benchmark.build_instances().values()))[0]
    serialized = task.model_dump(mode="json")
    rubric_json = serialized["evaluators"][0]
    judges = [
        c
        for c in rubric_json["criteria"]
        if c.get("_type", "").endswith(":JudgeCriterion")
    ]
    assert judges, "rubric must contain at least one JudgeCriterion"
    assert judges[0]["judge_model"], "judge_model must round-trip in JSON"
```

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py -q
```

## Task 8: Commit

```bash
git add ergon_builtins/ergon_builtins/sandboxes/research_e2b.py \
        ergon_builtins/ergon_builtins/toolkits/research_rubrics.py \
        ergon_builtins/ergon_builtins/benchmarks/researchrubrics/ \
        ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py \
        ergon_cli/ergon_cli/commands/_registry.py
git commit -m "feat(builtins): convert ResearchRubrics to object-bound Task (PR 10b)"
```

## PR Ledger

Invariant landed: ResearchRubrics builtin constructs object-bound task
graphs; `JudgeCriterion` is a Pydantic-persistent criterion subclass.

Bridge code introduced: `ResearchE2BSandbox` wraps the legacy manager
via `ManagerBackedSandboxRuntime` (the shared adapter PR 10a created).

Bridge code retired (partially):
- ResearchRubrics tasks now carry `task.worker`/`task.sandbox` inline,
  so ResearchRubrics runs no longer hit the `_legacy_worker_bridge`
  fallback that PR 5 Task 4b put on `worker_execute`. The fallback
  itself stays alive — it still serves gdpeval until it migrates in
  PR 10c. PR 11 deletes the fallback once every benchmark is on
  object-bound `Task`.

Old path still intentionally alive: `researchrubrics/sandbox_manager.py`,
registry registrations, and `_legacy_worker_bridge.py` (still required
by gdpeval).

Deletion gate: PR 11 deletes the manager file and registry registrations.
PR 10c's cross-cutting cleanup verifies migrated benchmarks no longer
import `ComponentRegistry`.

Tests added or updated: ResearchRubrics definition JSON + judge model
round-trip.

Modules owned by this PR: `researchrubrics/`, the ResearchRubrics
toolkit, and `JudgeCriterion`.
