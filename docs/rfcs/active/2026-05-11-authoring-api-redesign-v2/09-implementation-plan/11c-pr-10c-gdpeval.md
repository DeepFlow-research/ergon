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
ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox.py             # was sandboxes/gdpeval.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/toolkit.py             # was toolkits/gdpeval.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/_tools.py              # runtime tool construction
ergon_builtins/tests/unit/test_gdpeval_v2_definition.py
ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py
```

**Rename:**

```text
ergon_builtins/ergon_builtins/benchmarks/gdpeval/worker_factory.py
    → ergon_builtins/ergon_builtins/benchmarks/gdpeval/workers.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/gdpeval/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/rubric.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria.py
ergon_builtins/ergon_builtins/registry.py
ergon_builtins/ergon_builtins/registry_core.py
ergon_builtins/ergon_builtins/registry_data.py
ergon_builtins/ergon_builtins/benchmarks/README.md          # add GDPEval row
```

**Note: no `ergon_cli/_registry.py` edit.**  PR 6.5 deleted `BUILTIN_EXPERIMENT_FACTORIES`.

## Task 1: Add `GDPEvalSandbox`

GDPEval today has `sandbox.py` (the manager) and `sandbox_utils.py`.  The existing `sandbox.py` conflicts with the new `Sandbox` subclass file we want to create.  Rename the manager first to match the convention used by MiniF2F / SWEBench / ResearchRubrics:

- [ ] **Step 0: Rename existing `sandbox.py` → `sandbox_manager.py`**

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox.py \
       ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox_manager.py
```

Update every import of `GDPEvalSandboxManager` to use the new path:

```bash
rg "from ergon_builtins.benchmarks.gdpeval.sandbox import" ergon_builtins ergon_core
```

Replace with `from ergon_builtins.benchmarks.gdpeval.sandbox_manager import GDPEvalSandboxManager`.

- [ ] **Step 1: Create subclass**

`ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox.py` (now free after Step 0):

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.gdpeval.sandbox_manager import (
    GDPEvalSandboxManager,
)
from ergon_builtins.sandbox._manager_backed import (
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

- [ ] **Step 1: Convert existing `toolkit.py` to Pydantic in place**

`toolkit.py` already lives at `benchmarks/gdpeval/toolkit.py` — no move needed.  Do not create `ergon_builtins/toolkits/gdpeval.py` (PR 6.5 deleted the top-level `toolkits/` dir).

- [ ] **Step 2: Convert to Pydantic**

```python
from pydantic import BaseModel, ConfigDict


class GDPEvalToolkit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    output_path: str = "/workspace/gdpeval/output.json"
    allow_shell: bool = False

    def tools(self, sandbox, task):
        from ergon_builtins.benchmarks.gdpeval._tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move runtime tool construction into `benchmarks/gdpeval/_tools.py`.

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry call**

In `gdpeval/workers.py` (renamed from `worker_factory.py`):

```python
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
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

**Also: parameterise `GDPEvalBenchmark.__init__`** to accept `worker_factory` / `sandbox_factory` kwargs with defaults — mirror PR 6.5's MiniF2F pattern.

## Task 4: Convert Benchmark Tasks

- [ ] **Step 1: Replace imports**

```python
# Delete:
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec

# Add:
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.workers import (
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

## Task 5: Add GDPEval To The Benchmarks Catalogue

**Files:**

- Modify: `ergon_builtins/ergon_builtins/benchmarks/README.md` (created in PR 6.5 Task 20)

PR 6.5 killed `BUILTIN_EXPERIMENT_FACTORIES` and the CLI authoring route.  No CLI registry entry needed.

- [ ] **Step 1: Add one row to the catalogue**

```markdown
| GDPEval | `ergon_builtins.benchmarks.gdpeval` | `make_gdpeval_worker` | `GDPEvalSandbox` |
```

- [ ] **Step 2: Add a Python authoring example**

```python
from ergon_builtins.benchmarks.gdpeval import (
    GDPEvalBenchmark,
    make_gdpeval_worker,
)
from ergon_core.api import persist_benchmark, launch_run

benchmark = GDPEvalBenchmark(
    name="gdpeval-react",
    metadata={"experiment": "gdp-eval-2026"},
    worker_factory=make_gdpeval_worker,
    limit=10,
)
handle = persist_benchmark(benchmark)
await launch_run(handle.definition_id)
```

## Task 5.5: Migrate The Matching Smoke Fixture (closes the gate)

**Files:**

- Modify: `tests/fixtures/smoke_components/benchmarks.py` — `GDPEvalSmokeBenchmark` (or whichever subclass exists; add one if not)

PR 6 (minif2f), PR 10a (swebench), PR 10b (researchrubrics) each
migrated their matching smoke-fixture row. PR 10c does the last one.
After this step, **`tests/fixtures/smoke_components/benchmarks.py`
imports `Task` (not `TaskSpec`) for every benchmark** — which is the
prerequisite PR 11 needs to delete `TaskSpec` outright.

- [ ] **Step 1: Add a concrete `GDPEvalSmokeTask(Task[...])` subclass**
- [ ] **Step 2: Override `build_instances` to return that Task with `evaluators=(...)`** (mirror the prior three smoke-fixture migrations)
- [ ] **Step 3: Sweep the file for any remaining `TaskSpec` references** — after this PR, the import line should drop `TaskSpec` entirely.
- [ ] **Step 4: Update `_SingleTaskSmokeBenchmark` base class** — once every subclass overrides `build_instances`, the base's `TaskSpec`-shaped default can be deleted. Either delete the base method (preferred — each subclass owns its build) or convert it to raise `NotImplementedError`.

## Task 6: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_gdpeval_v2_definition.py`:

```python
import pytest
from ergon_core.api import persist_benchmark
from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark


@pytest.mark.asyncio
async def test_gdpeval_persists_object_bound_task_json(session_factory):
    benchmark = GDPEvalBenchmark(
        name="gdpeval-smoke",
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
git add ergon_builtins/ergon_builtins/benchmarks/gdpeval/ \
        ergon_builtins/ergon_builtins/benchmarks/README.md \
        ergon_builtins/ergon_builtins/registry*.py \
        ergon_builtins/tests/unit/test_gdpeval_v2_definition.py \
        ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py
git commit -m "feat(builtins): convert GDPEval + close out builtins migration (PR 10c)"
```

## PR Ledger

Invariant landed: GDPEval builtin constructs object-bound task graphs;
every migrated benchmark is `ComponentRegistry`-free; registry modules
are slimmed to model-backend registrations only.

Bridge code introduced: `GDPEvalSandbox` wraps the legacy manager via
`ManagerBackedSandboxRuntime`.

Bridge code retired (fully — after this PR's smoke-fixture migration):
- GDPEval tasks now carry `task.worker`/`task.sandbox`/`task.evaluators`
  inline, so GDPEval runs no longer hit either the
  `_legacy_worker_bridge` fallback on `worker_execute` or the symmetric
  `_legacy_evaluator_bridge` fallback on `evaluate_task_run`.
- After PR 10c + the smoke-fixture migration in Task 6.5, **no
  benchmark — production or smoke fixture — still produces `TaskSpec`**.
  The "must support" sets for both `_legacy_worker_bridge` and
  `_legacy_evaluator_bridge` are empty.
- The two bridge files are not deleted here; PR 11 owns the `git rm`
  plus the `if worker is None:` and `if not task.evaluators:` branch
  removals in `worker_execute.py` and `evaluate_task_run.py`.

Old path still intentionally alive: `gdpeval/sandbox.py`,
`gdpeval/sandbox_utils.py`, slimmed `registry*.py` modules,
`BaseSandboxManager`, all per-benchmark `sandbox_manager.py` files (kept
until PR 11 deletes them in one sweep), `_legacy_worker_bridge.py`,
and `_legacy_evaluator_bridge.py` (both unreachable from any benchmark
after this PR, but the files stay until PR 11 removes them together
with the matching fallback branches).

Migrations: this PR adds **no Alembic migration** (code-only changes).
Next free migration id is `aabbccdd0005` (PR 7 reserves `aabbccdd0004`;
PR 10a / 10b do not add migrations).

Deletion gate: PR 11 deletes the registry modules, per-benchmark
sandbox managers, `_legacy_worker_bridge.py`, and
`_legacy_evaluator_bridge.py`.

Tests added or updated: GDPEval definition JSON + reconstruction +
no-registry architecture guard across all four migrated benchmarks.

Modules owned by this PR: `gdpeval/`, the GDPEval toolkit, the
registry import shrink, and the cross-cutting no-registry guard.
