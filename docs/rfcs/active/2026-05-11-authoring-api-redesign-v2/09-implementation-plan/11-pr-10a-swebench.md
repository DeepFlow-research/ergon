# PR 10a — SWEBench Verified Vertical

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SWEBench tasks construct object-bound `Task` with
`SWEBenchSandbox` and a serializable solver worker.

**Architecture:** Repeat the MiniF2F vertical pattern (PR 6) for
SWEBench. Land as a standalone PR so the conversion fits the 2.5k
non-generated-changed-lines budget and reviewers can focus on one
benchmark at a time.

**Tech Stack:** Builtin benchmark modules, sandbox adapters, Pydantic
worker config, pytest.

This is the **first of three independent sub-PRs** that complete the
builtins migration. PR 10b (ResearchRubrics) and PR 10c (GDPEval) follow
the same template. Each can ship independently — there are no
sequential dependencies between the three, only the shared post-merge
cleanup that PR 10c executes.

---

## Common Conversion Recipe

Every vertical sub-PR (10a, 10b, 10c) follows the same template:

1. Create `Sandbox` subclass under `ergon_builtins/ergon_builtins/sandboxes/`.
2. Move sandbox provisioning behavior into the subclass's `provision()`
   body, attaching `_runtime` via `ManagerBackedSandboxRuntime`.
3. Add `_bind_runtime(sandbox_id)` so eval workers can attach to an
   already-running sandbox.
4. Move reusable toolkit construction into a serializable Pydantic
   object under `ergon_builtins/ergon_builtins/toolkits/`.
5. Convert `worker_factory.py` to return a concrete `Worker` instance
   that gets embedded in `Task.worker`.
6. Convert `benchmark.py` to return `Task` (not `TaskSpec`).
7. Add a unit test that persists the benchmark and asserts the stored
   task JSON has `_type` entries for `worker`, `sandbox`, and every
   `evaluators[i]`.
8. Leave the old `sandbox_manager.py` and registry registrations in
   place; PR 11 deletes them.

The `ManagerBackedSandboxRuntime` adapter is shared infrastructure —
PR 10a creates it; PR 10b and PR 10c import it.

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/sandboxes/swebench.py
ergon_builtins/ergon_builtins/sandboxes/_manager_backed.py
ergon_builtins/ergon_builtins/toolkits/swebench.py
ergon_builtins/tests/unit/test_swebench_v2_definition.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/rubric.py
ergon_core/tests/unit/runtime/test_experiment_definition_service.py
ergon_cli/ergon_cli/commands/_registry.py        # add the slug factory
```

## Task 1: Add `SWEBenchSandbox`

- [ ] **Step 1: Extract the shared `ManagerBackedSandboxRuntime`**

Create `ergon_builtins/ergon_builtins/sandboxes/_manager_backed.py` so
PR 10b and PR 10c can reuse it:

```python
"""Adapter that lets a Sandbox subclass delegate to a legacy
*SandboxManager.

PR 10a creates this; PR 10b and PR 10c import it. PR 11 deletes the
managers it wraps (after the SandboxRuntime protocol becomes the only
contract).
"""

from typing import Any


class ManagerBackedSandboxRuntime:
    """Adapter that lets a sandbox subclass delegate to a legacy manager."""

    def __init__(self, *, manager: Any, sandbox: Any) -> None:
        self._manager = manager
        self._sandbox = sandbox
        self.sandbox_id: str = sandbox.sandbox_id

    async def run_command(self, cmd, *, timeout=None):
        return await self._manager.run_command(
            self._sandbox.task_id, cmd, timeout=timeout
        )

    async def write_file(self, path: str, content: bytes) -> None:
        await self._manager.upload_file(self._sandbox.task_id, path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._manager.read_file(self._sandbox.task_id, path)

    async def list_files(self, path: str) -> list[str]:
        return await self._manager.list_files(self._sandbox.task_id, path)

    async def close(self) -> None:
        # Terminate the external sandbox AND drop local resources.
        await self._manager.terminate(self._sandbox.task_id)

    async def close_local(self) -> None:
        # Drop local handles only; leave the external sandbox alive so
        # the orchestrator's release can be the sole terminator.
        await self._manager.close_local(self._sandbox.task_id)
```

If a manager's API differs (e.g. `delete` instead of `terminate`, no
`close_local`), fix it at the manager layer rather than diverging the
adapter — every `*SandboxManager` ends up with the same five
operations.

PR 6's `LeanSandbox` (which inlined this adapter) must be updated in
this PR to import from the shared location. The edit is mechanical;
include it as part of Step 1.

- [ ] **Step 2: Create the SWEBench subclass**

`ergon_builtins/ergon_builtins/sandboxes/swebench.py`:

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.sandboxes._manager_backed import (
    ManagerBackedSandboxRuntime,
)


class SWEBenchSandbox(Sandbox):
    """E2B-backed sandbox for SWEBench verified instances."""

    image_tag: str = "ergon-swebench-v1"
    repo_url: str | None = None
    base_commit: str | None = None
    requires_network: bool = True

    async def provision(self) -> None:
        manager = SWEBenchSandboxManager(
            image_tag=self.image_tag,
            repo_url=self.repo_url,
            base_commit=self.base_commit,
        )
        sandbox = await manager.create(task_id=uuid4(), envs=self.env)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )

    async def _bind_runtime(self, sandbox_id: str) -> None:
        # Eval-side attach: reconnect to an already-running sandbox.
        manager = SWEBenchSandboxManager(
            image_tag=self.image_tag,
            repo_url=self.repo_url,
            base_commit=self.base_commit,
        )
        sandbox = await manager.connect(sandbox_id=sandbox_id)
        object.__setattr__(
            self,
            "_runtime",
            ManagerBackedSandboxRuntime(manager=manager, sandbox=sandbox),
        )
```

If `SWEBenchSandboxManager` does not expose `connect(sandbox_id=...)`,
add the method at the manager layer — every benchmark's manager must
support reconnect-by-id for the synchronous-fanout eval path to work.

## Task 2: Move Toolkit Construction

- [ ] **Step 1: Move toolkit to shared location**

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py \
       ergon_builtins/ergon_builtins/toolkits/swebench.py
```

- [ ] **Step 2: Convert toolkit to Pydantic BaseModel**

`SWEBenchToolkit` must be a `BaseModel` so `Worker.toolkit` round-trips
through `_type` discrimination. The toolkit holds **config**, not
runtime handles:

```python
from pydantic import BaseModel, ConfigDict


class SWEBenchToolkit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    repo_root: str = "/workspace/repo"
    patch_output_path: str = "/workspace/final_output/patch.diff"
    max_tool_calls: int = 32

    def tools(self, sandbox, task):
        # Lazy import keeps runtime tool construction out of the
        # serialization path.
        from ergon_builtins.toolkits._swebench_tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move runtime tool construction into a sibling `_swebench_tools.py`
module; the toolkit serializes; the tools do not.

- [ ] **Step 3: Update all importers**

```bash
rg "from ergon_builtins.benchmarks.swebench_verified.toolkit import" \
  ergon_builtins ergon_core
```

Replace with `from ergon_builtins.toolkits.swebench import SWEBenchToolkit`.

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry-driven factory with direct constructor**

In `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/worker_factory.py`:

```python
from ergon_builtins.toolkits.swebench import SWEBenchToolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker


def make_swebench_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 24,
) -> ReActWorker:
    return ReActWorker(
        name="swebench-solver",
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=SWEBenchToolkit(),
    )
```

PR 6's `ReActWorker.toolkit` field gains the `SWEBenchToolkit` member
of its union (or, if `ReActWorker.toolkit` is a `Toolkit` protocol,
SWEBench's toolkit automatically satisfies it). Update PR 6's worker
module type union in the same commit.

## Task 4: Convert Benchmark Tasks

- [ ] **Step 1: Replace imports**

In `benchmark.py`:

```python
# Delete:
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec

# Add:
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.sandboxes.swebench import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.worker_factory import (
    make_swebench_worker,
)
from ergon_builtins.benchmarks.swebench_verified.rubric import (
    make_swebench_rubric,
)
```

- [ ] **Step 2: Replace `TaskSpec` construction**

Every `TaskSpec(...)` call inside `build_instances` becomes:

```python
Task[SWEBenchTaskPayload](
    task_slug="swebench-instance",
    instance_key=instance.instance_id,
    description=instance.problem_statement,
    task_payload=SWEBenchTaskPayload(
        instance_id=instance.instance_id,
        repo=instance.repo,
        base_commit=instance.base_commit,
    ),
    worker=make_swebench_worker(),
    sandbox=SWEBenchSandbox(
        repo_url=f"https://github.com/{instance.repo}",
        base_commit=instance.base_commit,
    ),
    evaluators=(make_swebench_rubric(),),
)
```

## Task 5: Add CLI Factory Entry

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/_registry.py`

- [ ] **Step 1: Register the SWEBench experiment factory**

Per PR 8's "Adding a builtin factory" pattern, append to
`BUILTIN_EXPERIMENT_FACTORIES`:

```python
from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SWEBenchVerifiedBenchmark,
)


def _swebench() -> Experiment:
    return Experiment(
        benchmark=SWEBenchVerifiedBenchmark(),
        name="swebench-verified",
        description="SWE-bench Verified instances against object-bound API.",
        metadata={"source": "builtins"},
    )


BUILTIN_EXPERIMENT_FACTORIES["swebench-verified"] = _swebench
```

If the dict is built with literal initialization, add the entry to the
literal and re-export `_swebench` for testability.

## Task 6: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_swebench_v2_definition.py`:

```python
import pytest
from ergon_core.api import Experiment
from ergon_core.core.application.experiments.definition_writer import (
    persist_definition,
)
from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SWEBenchVerifiedBenchmark,
)


@pytest.mark.asyncio
async def test_swebench_persists_object_bound_task_json(session_factory):
    benchmark = SWEBenchVerifiedBenchmark(limit=1)
    experiment = Experiment(
        benchmark=benchmark,
        name="swebench-smoke",
        metadata={"created_by": "test"},
    )

    handle = persist_definition(experiment)
    with session_factory() as session:
        rows = session.exec(
            "SELECT task_json FROM experiment_definition_tasks "
            "WHERE definition_id = :d",
            {"d": handle.definition_id},
        ).all()
    assert rows, "expected at least one persisted task"
    task_json = rows[0][0]
    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["sandbox"]["_type"].endswith(":SWEBenchSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(
        ev.get("_type") for ev in task_json["evaluators"]
    ), "every evaluator entry must carry a `_type` discriminator"
    assert "_legacy" not in task_json
```

- [ ] **Step 2: Reconstruction test**

```python
from uuid import uuid4

import pytest
from ergon_core.api.benchmark.task import Task


@pytest.mark.asyncio
async def test_swebench_task_json_round_trips_through_from_definition():
    benchmark = SWEBenchVerifiedBenchmark(limit=1)
    task = next(iter(benchmark.build_instances().values()))[0]
    task_json = task.model_dump(mode="json")

    rebuilt = await Task.from_definition(task_json, task_id=uuid4())

    assert rebuilt.worker is not None
    assert rebuilt.sandbox is not None
    assert isinstance(rebuilt.sandbox, type(task.sandbox))
```

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_builtins/tests/unit/test_swebench_v2_definition.py \
  ergon_core/tests/unit/runtime/test_experiment_definition_service.py -q
```

Expected: pass; persisted JSON includes object-bound `_type`s for
worker, sandbox, and every evaluator entry.

## Task 7: Commit

```bash
git add ergon_builtins/ergon_builtins/sandboxes/swebench.py \
        ergon_builtins/ergon_builtins/sandboxes/_manager_backed.py \
        ergon_builtins/ergon_builtins/toolkits/swebench.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/worker_factory.py \
        ergon_builtins/tests/unit/test_swebench_v2_definition.py \
        ergon_cli/ergon_cli/commands/_registry.py
git commit -m "feat(builtins): convert SWEBench to object-bound Task (PR 10a)"
```

## PR Ledger

Invariant landed: SWEBench builtin constructs object-bound task graphs;
shared `ManagerBackedSandboxRuntime` adapter exists for PR 10b/10c.

Bridge code introduced: `SWEBenchSandbox` wraps the legacy
`SWEBenchSandboxManager` via `ManagerBackedSandboxRuntime`; toolkit is
Pydantic-serializable.

Bridge code retired (partially):
- SWEBench tasks now carry `task.worker`/`task.sandbox` inline, so
  SWEBench runs no longer hit the `_legacy_worker_bridge` fallback that
  PR 5 Task 4b put on `worker_execute`. The fallback itself stays alive
  — it still serves researchrubrics and gdpeval until they migrate in
  PR 10b/10c. PR 11 deletes the fallback once every benchmark is on
  object-bound `Task`.

Old path still intentionally alive: `swebench_verified/sandbox_manager.py`,
registry registrations in `ergon_builtins/registry*.py`, the unmigrated
MiniF2F inline adapter (Step 1 above migrates it), and
`_legacy_worker_bridge.py` (still required by researchrubrics and
gdpeval).

Deletion gate: PR 11 deletes the manager file and registry registrations.
PR 10c's cross-cutting cleanup verifies migrated benchmarks no longer
import `ComponentRegistry`.

Tests added or updated: SWEBench definition JSON + reconstruction.

Modules owned by this PR: `swebench_verified/`, the shared sandbox
adapter, and the SWEBench toolkit.
