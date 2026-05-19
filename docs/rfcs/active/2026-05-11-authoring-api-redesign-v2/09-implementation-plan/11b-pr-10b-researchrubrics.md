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
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/sandbox.py    # was sandboxes/research_e2b.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/toolkit.py    # was toolkits/research_rubrics.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/_tools.py     # runtime tool construction
ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py
```

**Rename:**

```text
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/worker_factory.py
    → ergon_builtins/ergon_builtins/benchmarks/researchrubrics/workers.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/criteria.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py
ergon_builtins/ergon_builtins/benchmarks/README.md      # add ResearchRubrics row
```

**Note: no `ergon_cli/_registry.py` edit.**  PR 6.5 deleted `BUILTIN_EXPERIMENT_FACTORIES`.  Discovery is via the README catalogue; authoring is Python-only.

## Task 1: Add `ResearchE2BSandbox`

- [ ] **Step 1: Create the subclass**

`ergon_builtins/ergon_builtins/benchmarks/researchrubrics/sandbox.py`:

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import (
    ResearchRubricsSandboxManager,
)
from ergon_builtins.sandbox._manager_backed import (
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

The shared `ManagerBackedSandboxRuntime` is the one PR 10a landed at `ergon_builtins/sandbox/_manager_backed.py` (singular `sandbox/`, top-level — PR 6.5 created the empty package).  If PR 10b lands first (rather than after 10a), create the adapter as Step 0 — see PR 10a's Task 1 Step 1 for the exact body.

## Task 2: Move Toolkit Helpers

- [ ] **Step 1: Move toolkit types**

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/researchrubrics/toolkit_types.py \
       ergon_builtins/ergon_builtins/benchmarks/researchrubrics/toolkit.py
```

**Do NOT create `ergon_builtins/toolkits/`** — PR 6.5 deleted that top-level dir.  Toolkit lives alongside its benchmark.

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
        from ergon_builtins.benchmarks.researchrubrics._tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move runtime tool construction into `benchmarks/researchrubrics/_tools.py`; the toolkit holds config only.

- [ ] **Step 3: Update importers**

```bash
rg "from ergon_builtins.benchmarks.researchrubrics.toolkit_types import" \
  ergon_builtins ergon_core
rg "from ergon_builtins.toolkits" \   # should be zero hits — PR 6.5 deleted the dir
  ergon_builtins ergon_core
```

Replace with `from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit`.

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry call with constructor**

In `researchrubrics/workers.py` (renamed from `worker_factory.py` — mirror PR 6.5's MiniF2F rename):

```python
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
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

**Also: parameterise `ResearchRubricsBenchmark.__init__`** to accept `worker_factory` / `sandbox_factory` kwargs with defaults — mirror the PR 6.5 MiniF2F pattern.  This makes the worker swap point real for Python authoring.

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
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.workers import (
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

## Task 6: Add ResearchRubrics To The Benchmarks Catalogue

**Files:**

- Modify: `ergon_builtins/ergon_builtins/benchmarks/README.md` (created in PR 6.5 Task 20)

PR 6.5 killed `BUILTIN_EXPERIMENT_FACTORIES` and the entire CLI authoring route.  No CLI registry entry needed.

- [ ] **Step 1: Add one row to the catalogue**

```markdown
| ResearchRubrics | `ergon_builtins.benchmarks.researchrubrics` | `make_research_worker` | `ResearchE2BSandbox` |
```

- [ ] **Step 2: Add a Python authoring example**

```python
from ergon_builtins.benchmarks.researchrubrics import (
    ResearchRubricsBenchmark,
    make_research_worker,
)
from ergon_core.api import persist_benchmark, launch_run

benchmark = ResearchRubricsBenchmark(
    name="research-react",
    metadata={"experiment": "rr-eval-2026"},
    worker_factory=make_research_worker,
    limit=10,
)
handle = persist_benchmark(benchmark)
await launch_run(handle.definition_id)
```

## Task 6.5: Migrate The Matching Smoke Fixture

**Files:**

- Modify: `tests/fixtures/smoke_components/benchmarks.py` — `ResearchRubricsSmokeBenchmark`
- Modify: `tests/fixtures/smoke_components/criteria/smoke_rubrics.py` — `ResearchRubricsSmokeRubric`

Symmetric with PR 10a's smoke-fixture migration. The production
ResearchRubrics benchmark migrates to `Task` here, but the smoke
fixture at `tests/fixtures/smoke_components/benchmarks.py` still uses
`TaskSpec`. Migrate it in lockstep so `_legacy_evaluator_bridge` and
`_legacy_worker_bridge` get one step closer to deletable.

- [ ] **Step 1: Add `ResearchRubricsSmokeTask(Task[...])` concrete subclass**
- [ ] **Step 2: Override `build_instances` to return that Task with `evaluators=(...)`** (mirror PR 6 minif2f + PR 10a swebench)
- [ ] **Step 3: Migrate `ResearchRubricsSmokeRubric` to pure Pydantic** (drop custom `__init__`; use `model_validator(mode="after")` to build criteria)

## Task 7: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py`:

```python
import pytest
from ergon_core.api import persist_benchmark
from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)


@pytest.mark.asyncio
async def test_research_rubrics_persists_object_bound_task_json(session_factory):
    benchmark = ResearchRubricsBenchmark(
        name="research-smoke",
        metadata={"author": "test"},
        limit=1,
    )

    handle = persist_benchmark(benchmark)
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
git add ergon_builtins/ergon_builtins/benchmarks/researchrubrics/ \
        ergon_builtins/ergon_builtins/benchmarks/README.md \
        ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py
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
  fallback on `worker_execute`.
- ResearchRubrics tasks also carry `task.evaluators` inline, so they no
  longer hit the symmetric `_legacy_evaluator_bridge` fallback on
  `evaluate_task_run`. (Particularly relevant here since ResearchRubrics
  is judge-driven and lives on the eval side.)
- Both fallbacks stay alive — they still serve gdpeval and any
  unmigrated smoke fixtures until PR 10c migrates them. PR 11 deletes
  both bridges once every benchmark is on object-bound `Task`.

Old path still intentionally alive: `researchrubrics/sandbox_manager.py`,
registry registrations, `_legacy_worker_bridge.py`, and
`_legacy_evaluator_bridge.py` (the last two still required by gdpeval).

Migrations: this PR adds **no Alembic migration** (the change is
code-only). If a migration is needed, it claims `aabbccdd0006` (PR 6.5
took `aabbccdd0004` for `add_experiment_tag`; PR 7 took `aabbccdd0005`
for `definition_metadata_and_launch`; PR 10a does not add one).

Deletion gate: PR 11 deletes the manager file and registry registrations.
PR 10c's cross-cutting cleanup verifies migrated benchmarks no longer
import `ComponentRegistry`.

Tests added or updated: ResearchRubrics definition JSON + judge model
round-trip.

Modules owned by this PR: `researchrubrics/`, the ResearchRubrics
toolkit, and `JudgeCriterion`.
