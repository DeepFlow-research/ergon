# PR 10c — GDPEval Vertical + Builtins Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GDPEval tasks construct object-bound `Task` with
`GDPEvalSandbox` and a serializable evaluator worker. Additionally, the
final vertical runs the cross-cutting cleanup: a registry-import guard
that verifies every migrated benchmark has stopped depending on
`ComponentRegistry`.

**Architecture:** Repeat the MiniF2F + SWEBench + ResearchRubrics
vertical pattern for GDPEval. Add the post-migration cleanup that
PRs 6 / 10a / 10b together enable.

**Tech Stack:** Builtin benchmark modules, sandbox adapters, Pydantic
worker config, pytest, textual architecture guards.

PR 10c **must merge last** of the three sub-PRs — its cleanup
asserts every migrated benchmark (minif2f, swebench_verified,
researchrubrics, gdpeval) is `ComponentRegistry`-free, which is only
true once 10a, 10b, and 10c are all in.

---

## Common Conversion Recipe

See [`11-pr-10a-swebench.md`](11-pr-10a-swebench.md) § Common
Conversion Recipe.

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/sandboxes/gdpeval.py
ergon_builtins/ergon_builtins/toolkits/gdpeval.py
ergon_builtins/tests/unit/test_gdpeval_v2_definition.py
ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/gdpeval/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/rubric.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria.py
ergon_builtins/ergon_builtins/registry.py
ergon_builtins/ergon_builtins/registry_core.py
ergon_builtins/ergon_builtins/registry_data.py
ergon_cli/ergon_cli/commands/_registry.py        # add the slug factory
```

## Task 1: Add `GDPEvalSandbox`

GDPEval today has both `sandbox.py` and `sandbox_utils.py`. Move the
provisioning entry point into the new subclass.

- [ ] **Step 1: Create subclass**

`ergon_builtins/ergon_builtins/sandboxes/gdpeval.py`:

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.gdpeval.sandbox import (
    GDPEvalSandboxManager,
)
from ergon_builtins.sandboxes._manager_backed import (
    ManagerBackedSandboxRuntime,
)


class GDPEvalSandbox(Sandbox):
    template_id: str = "ergon-gdpeval-v1"
    requires_network: bool = False
    workspace_dir: str = "/workspace/gdpeval"

    async def provision(self) -> None:
        manager = GDPEvalSandboxManager(template_id=self.template_id)
        sandbox = await manager.create(task_id=uuid4(), envs=self.env)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )

    async def _bind_runtime(self, sandbox_id: str) -> None:
        manager = GDPEvalSandboxManager(template_id=self.template_id)
        sandbox = await manager.connect(sandbox_id=sandbox_id)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )
```

If `GDPEvalSandboxManager` does not expose
`create / run_command / upload_file / read_file / list_files / terminate / connect`,
add thin adapter methods at the manager — do not reshape the
`SandboxRuntime` protocol.

## Task 2: Move Toolkit

- [ ] **Step 1: Move toolkit**

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/gdpeval/toolkit.py \
       ergon_builtins/ergon_builtins/toolkits/gdpeval.py
```

- [ ] **Step 2: Convert to Pydantic**

```python
from pydantic import BaseModel, ConfigDict


class GDPEvalToolkit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    output_path: str = "/workspace/gdpeval/output.json"
    allow_shell: bool = False

    def tools(self, sandbox, task):
        from ergon_builtins.toolkits._gdpeval_tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry call**

```python
from ergon_builtins.toolkits.gdpeval import GDPEvalToolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker


def make_gdpeval_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 12,
) -> ReActWorker:
    return ReActWorker(
        name="gdpeval-runner",
        model=model,
        system_prompt=_GDPEVAL_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=GDPEvalToolkit(),
    )
```

## Task 4: Convert Benchmark Tasks

- [ ] **Step 1: Replace imports**

```python
# Delete:
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec

# Add:
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.sandboxes.gdpeval import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.worker_factory import (
    make_gdpeval_worker,
)
from ergon_builtins.benchmarks.gdpeval.rubric import make_gdpeval_rubric
```

- [ ] **Step 2: Replace `TaskSpec` construction**

```python
Task[GDPEvalTaskPayload](
    task_slug="gdpeval-instance",
    instance_key=instance.instance_id,
    description=instance.prompt,
    task_payload=GDPEvalTaskPayload(
        instance_id=instance.instance_id,
        question=instance.prompt,
        expected=instance.expected,
    ),
    worker=make_gdpeval_worker(),
    sandbox=GDPEvalSandbox(),
    evaluators=(make_gdpeval_rubric(),),
)
```

## Task 5: Add CLI Factory Entry

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/_registry.py`

- [ ] **Step 1: Register the GDPEval experiment factory**

```python
from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark


def _gdpeval() -> Experiment:
    return Experiment(
        benchmark=GDPEvalBenchmark(),
        name="gdpeval",
        description="GDPEval benchmark on object-bound API.",
        metadata={"source": "builtins"},
    )


BUILTIN_EXPERIMENT_FACTORIES["gdpeval"] = _gdpeval
```

## Task 6: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_gdpeval_v2_definition.py`:

```python
import pytest
from ergon_core.api import Experiment
from ergon_core.core.application.experiments.definition_writer import (
    persist_definition,
)
from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark


@pytest.mark.asyncio
async def test_gdpeval_persists_object_bound_task_json(session_factory):
    benchmark = GDPEvalBenchmark(limit=1)
    experiment = Experiment(
        benchmark=benchmark,
        name="gdpeval-smoke",
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
    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["sandbox"]["_type"].endswith(":GDPEvalSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(
        ev.get("_type") for ev in task_json["evaluators"]
    ), "every evaluator entry must carry a `_type` discriminator"
```

- [ ] **Step 2: Reconstruction test**

```python
from uuid import uuid4

import pytest
from ergon_core.api.benchmark.task import Task


@pytest.mark.asyncio
async def test_gdpeval_task_json_round_trips_through_from_definition():
    benchmark = GDPEvalBenchmark(limit=1)
    task = next(iter(benchmark.build_instances().values()))[0]
    task_json = task.model_dump(mode="json")

    rebuilt = await Task.from_definition(task_json, task_id=uuid4())

    assert isinstance(rebuilt.sandbox, type(task.sandbox))
    assert rebuilt.worker.toolkit is not None
```

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_builtins/tests/unit/test_gdpeval_v2_definition.py -q
```

## Task 7: Cross-Cutting Cleanup — Registry Import Shrink

After 10a / 10b / 10c land, no migrated benchmark module should import
`ComponentRegistry`. PR 10c verifies this with a textual guard test and
trims the registry modules' loader to only register the parts that
still have non-builtin callers (model backends, training pipelines).

**Files:**

- Modify: `ergon_builtins/ergon_builtins/registry.py`
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_builtins/ergon_builtins/registry_data.py`
- Create: `ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py`

- [ ] **Step 1: Remove migrated-benchmark imports from registry files**

In `registry.py`, `registry_core.py`, `registry_data.py`, delete the
import blocks and registration lines for each migrated benchmark.
Remaining registrations should only be model-backend or training-side
entries; if those don't exist, the file becomes a thin stub. Leave the
files importable until PR 11 — worktrees that haven't rebased still
need to import them.

- [ ] **Step 2: Add the no-registry guard**

Create `ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py`:

```python
"""After PR 10a/10b/10c land, no migrated benchmark module should
import `ComponentRegistry` — object-bound benchmarks construct Tasks
directly and don't go through registry resolution."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

_MIGRATED_BENCHMARKS = (
    "minif2f",
    "swebench_verified",
    "researchrubrics",
    "gdpeval",
)


@pytest.mark.parametrize("slug", _MIGRATED_BENCHMARKS)
def test_object_bound_benchmark_does_not_import_component_registry(
    slug: str,
) -> None:
    pkg = ROOT / "ergon_builtins" / "ergon_builtins" / "benchmarks" / slug
    offenders: list[str] = []
    for path in pkg.rglob("*.py"):
        text = path.read_text()
        if "ComponentRegistry" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        f"{slug} still depends on ComponentRegistry; PR 10 was supposed "
        f"to remove that dependency. Offenders: {offenders}"
    )
```

- [ ] **Step 3: Run the full builtins test sweep**

```bash
uv run pytest ergon_builtins/tests/unit -q
uv run pytest ergon_core/tests/unit/runtime/test_experiment_definition_service.py -q
uv run pytest ergon_core/tests/unit/architecture -q
```

Expected: all green; no `TaskSpec`, `ComponentRegistry`, or
`BaseSandboxManager` references inside object-bound benchmark modules.

## Task 8: Commit

```bash
git add ergon_builtins/ergon_builtins/sandboxes/gdpeval.py \
        ergon_builtins/ergon_builtins/toolkits/gdpeval.py \
        ergon_builtins/ergon_builtins/benchmarks/gdpeval/ \
        ergon_builtins/ergon_builtins/registry*.py \
        ergon_builtins/tests/unit/test_gdpeval_v2_definition.py \
        ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py \
        ergon_cli/ergon_cli/commands/_registry.py
git commit -m "feat(builtins): convert GDPEval + close out builtins migration (PR 10c)"
```

## PR Ledger

Invariant landed: GDPEval builtin constructs object-bound task graphs;
every migrated benchmark is `ComponentRegistry`-free; registry modules
are slimmed to model-backend registrations only.

Bridge code introduced: `GDPEvalSandbox` wraps the legacy manager via
`ManagerBackedSandboxRuntime`.

Bridge code retired (partially):
- GDPEval tasks now carry `task.worker`/`task.sandbox` inline, so
  GDPEval runs no longer hit the `_legacy_worker_bridge` fallback that
  PR 5 Task 4b put on `worker_execute`. After PR 10c, no benchmark
  still produces `TaskSpec` — the "must support" set for
  `_legacy_worker_bridge.legacy_worker_from_payload` is empty. The
  fallback file is not deleted here; PR 11 owns the `git rm` plus the
  `if worker is None:` branch removal in `worker_execute.py`.

Old path still intentionally alive: `gdpeval/sandbox.py`,
`gdpeval/sandbox_utils.py`, slimmed `registry*.py` modules,
`BaseSandboxManager`, all per-benchmark `sandbox_manager.py` files (kept
until PR 11 deletes them in one sweep), and `_legacy_worker_bridge.py`
(now unreachable from any benchmark, but the file stays until PR 11
removes it together with the `worker_execute` fallback branch).

Deletion gate: PR 11 deletes the registry modules, per-benchmark
sandbox managers, and `_legacy_worker_bridge.py`.

Tests added or updated: GDPEval definition JSON + reconstruction +
no-registry architecture guard across all four migrated benchmarks.

Modules owned by this PR: `gdpeval/`, the GDPEval toolkit, the
registry import shrink, and the cross-cutting no-registry guard.
