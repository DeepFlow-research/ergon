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

Every vertical sub-PR (10a, 10b, 10c) follows the same template.  PR 6.5 fixed the file layout + killed the `Experiment` class, so this recipe assumes the post-PR-6.5 world:

1. Create `Sandbox` subclass at **`ergon_builtins/ergon_builtins/benchmarks/<slug>/sandbox.py`** (per-benchmark, NOT under `sandboxes/` — PR 6.5 deleted that top-level dir).
2. Move sandbox provisioning behavior into the subclass's `provision()` body, attaching `_runtime` via `ManagerBackedSandboxRuntime` from `ergon_builtins/sandbox/_manager_backed.py` (singular, top-level — created by PR 10a; reused by PR 10b/10c).
3. Add `_bind_runtime(sandbox_id)` so eval workers can attach to an already-running sandbox.
4. Move reusable toolkit construction into a serializable Pydantic object at **`ergon_builtins/ergon_builtins/benchmarks/<slug>/toolkit.py`** (per-benchmark, NOT under `toolkits/`).
5. Add **`benchmarks/<slug>/workers.py`** (renamed from `worker_factory.py`) with factory functions like `make_<slug>_worker()` returning a concrete `Worker` instance.  Parameterise the benchmark constructor (`worker_factory=...`, `sandbox_factory=...`) following the PR 6.5 MiniF2F pattern.
6. Convert `benchmark.py` to return `Task` (not `TaskSpec`).
7. Add a unit test that persists the benchmark and asserts the stored task JSON has `_type` entries for `worker`, `sandbox`, and every `evaluators[i]`.
8. Add one line to **`ergon_builtins/ergon_builtins/benchmarks/README.md`** (the catalogue PR 6.5 added) listing this benchmark and its worker factories.
9. Leave the old `sandbox_manager.py` and registry registrations in place; PR 11 deletes them.

**No CLI factory registration step.**  PR 6.5 deleted `BUILTIN_EXPERIMENT_FACTORIES` and the entire CLI authoring route.  Authoring is Python-only — users import the benchmark class directly from `ergon_builtins.benchmarks.<slug>` and call `persist_benchmark(...)`.  The CLI observes via `ergon experiment show` / `ergon run status` (added in PR 8).

The `ManagerBackedSandboxRuntime` adapter is shared infrastructure — PR 10a creates it at `ergon_builtins/sandbox/_manager_backed.py`; PR 10b and PR 10c import from there.

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox.py        # was sandboxes/swebench.py
ergon_builtins/ergon_builtins/sandbox/_manager_backed.py                      # singular top-level; was sandboxes/_manager_backed.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py        # was toolkits/swebench.py
ergon_builtins/tests/unit/test_swebench_v2_definition.py
```

**Rename:**

```text
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/worker_factory.py
    → ergon_builtins/ergon_builtins/benchmarks/swebench_verified/workers.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/rubric.py
ergon_builtins/ergon_builtins/benchmarks/README.md                            # add SWEBench row
ergon_core/tests/unit/runtime/test_definition_writer.py
tests/fixtures/smoke_components/benchmarks.py            # migrate SweBenchSmokeBenchmark in lockstep
```

**Note: no `ergon_cli/ergon_cli/commands/_registry.py` edit.**  PR 6.5 deleted `BUILTIN_EXPERIMENT_FACTORIES`; there is no CLI registry to add an entry to.  The benchmark is discoverable via the `benchmarks/README.md` catalogue and importable from Python.

## Task 1: Add `SWEBenchSandbox`

- [ ] **Step 1: Extract the shared `ManagerBackedSandboxRuntime`**

Create `ergon_builtins/ergon_builtins/sandbox/_manager_backed.py` (PR 6.5 created the empty `sandbox/` package dir specifically for this file) so PR 10b and PR 10c can reuse it:

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

PR 6.5's `LeanSandbox` at `ergon_builtins/benchmarks/minif2f/sandbox.py` (which inlined this adapter) must be updated in this PR to import from the shared location:

```python
# Before (PR 6.5): the adapter was inlined inside benchmarks/minif2f/sandbox.py
# After (PR 10a): import from the shared module
from ergon_builtins.sandbox._manager_backed import ManagerBackedSandboxRuntime
```

The edit is mechanical; include it as part of Step 1.  PR 6.5's `# TODO(PR 10a):` markers on the inlined adapter point at this exact change.

- [ ] **Step 2: Resolve the `sandbox/` directory name conflict**

SWEBench currently has both `benchmarks/swebench_verified/sandbox_manager.py` (the manager) AND a `benchmarks/swebench_verified/sandbox/` *directory* containing `Dockerfile`, `e2b.toml.template`, and `utils.py`.  Creating a new `sandbox.py` file at the same level would shadow that directory in Python's module resolution.

Rename the directory first:

```bash
git mv ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox \
       ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_template
```

Update any `from ergon_builtins.benchmarks.swebench_verified.sandbox.utils import ...` imports to `sandbox_template.utils`.

- [ ] **Step 3: Create the SWEBench subclass**

`ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox.py`:

```python
from uuid import uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.sandbox._manager_backed import (
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

- [ ] **Step 1: Move toolkit into the per-benchmark subpackage**

If a `toolkit.py` already exists under `swebench_verified/`, that's the target path — no move needed.  If toolkit logic lives elsewhere, move it:

```bash
# Example if toolkit logic is currently in a sibling location:
git mv <current_path>/toolkit.py \
       ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py
```

**Do NOT create `ergon_builtins/toolkits/`** — PR 6.5 explicitly deleted that top-level dir as a misleading cross-cutting namespace.  Per-benchmark toolkits live alongside their benchmark.

- [ ] **Step 2: Convert toolkit to Pydantic BaseModel**

`SWEBenchToolkit` must be a `BaseModel` so `Worker.toolkit` round-trips through `_type` discrimination. The toolkit holds **config**, not runtime handles:

```python
from pydantic import BaseModel, ConfigDict


class SWEBenchToolkit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    repo_root: str = "/workspace/repo"
    patch_output_path: str = "/workspace/final_output/patch.diff"
    max_tool_calls: int = 32

    def tools(self, sandbox, task):
        # Lazy import keeps runtime tool construction out of the
        # serialization path.  PR 6.5's MiniF2FToolkit followed the
        # same pattern; reference its `# reason:` comment for the
        # circular-import rationale.
        from ergon_builtins.benchmarks.swebench_verified._tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move runtime tool construction into a sibling `_tools.py` module (under `benchmarks/swebench_verified/`); the toolkit serializes; the tools do not.

- [ ] **Step 3: Update all importers**

```bash
rg "from ergon_builtins.toolkits\b" ergon_builtins ergon_core   # should be zero hits — PR 6.5 deleted the dir
rg "from ergon_builtins.benchmarks.swebench_verified.toolkit import" \
  ergon_builtins ergon_core
```

The first command exists to fail loudly if anyone still references the deleted top-level `toolkits/`.  The second is what should resolve cleanly.

## Task 3: Convert Worker Factory

- [ ] **Step 1: Replace registry-driven factory with direct constructor**

In `ergon_builtins/benchmarks/swebench_verified/workers.py` (renamed from `worker_factory.py`):

```python
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
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

`ReActWorker.toolkit` field gains `SWEBenchToolkit` in its union (PR 6.5's `# TODO(PR 10a/10b/10c):` comment on the field flagged this).  Update the union in the same commit.  PR 11 collapses the union into a `Toolkit` protocol once 3+ toolkits exist.

**Also: parameterise `SWEBenchVerifiedBenchmark.__init__`** to accept `worker_factory` / `sandbox_factory` / `evaluator_factory` kwargs with defaults — mirror the PR 6.5 MiniF2F pattern.  This is what makes the worker swap point real for downstream `experiment.py` / Python authoring users.

## Task 4: Convert Benchmark Tasks

- [ ] **Step 1: Replace imports**

In `benchmark.py`:

```python
# Delete:
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec

# Add:
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.workers import (
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

## Task 5: Add SWEBench To The Benchmarks Catalogue

**Files:**

- Modify: `ergon_builtins/ergon_builtins/benchmarks/README.md` (created in PR 6.5 Task 20)

PR 6.5 killed `BUILTIN_EXPERIMENT_FACTORIES` and the entire CLI authoring route.  There is **no CLI registry to update**.  Discovery is documentation-only.

- [ ] **Step 1: Add one row to the catalogue**

Open `ergon_builtins/ergon_builtins/benchmarks/README.md` and add a row for SWEBench under the existing table:

```markdown
| SWEBench Verified | `ergon_builtins.benchmarks.swebench_verified` | `make_swebench_worker` | `SWEBenchSandbox` |
```

- [ ] **Step 2: Document the Python authoring example for SWEBench**

If the README has per-benchmark example snippets, add one for SWEBench mirroring the MiniF2F example PR 6.5 added:

```python
from ergon_builtins.benchmarks.swebench_verified import (
    SWEBenchVerifiedBenchmark,
    make_swebench_worker,
)
from ergon_core.api import persist_benchmark, launch_run

benchmark = SWEBenchVerifiedBenchmark(
    name="swebench-react",
    metadata={"experiment": "swebench-eval-2026"},
    worker_factory=make_swebench_worker,
    limit=10,
)
handle = persist_benchmark(benchmark)
await launch_run(handle.definition_id)
```

That's the entire "register the benchmark" workflow.  Users discover it via the README; they author runs via Python.

## Task 5.5: Migrate The Matching Smoke Fixture

**Files:**

- Modify: `tests/fixtures/smoke_components/benchmarks.py` — `SweBenchSmokeBenchmark`
- Modify (if needed): `tests/fixtures/smoke_components/criteria/smoke_rubrics.py` — `SweBenchSmokeRubric`

PR 5's retirement of `_evaluator_bridge` + PR 6's object-bound migration
created an asymmetry: the **production** SWEBench benchmark migrates to
`Task` here, but the **smoke fixture** at
`tests/fixtures/smoke_components/benchmarks.py` still uses `TaskSpec`.
Both must move together or PR 11 cannot delete `TaskSpec`.

- [ ] **Step 1: Add a concrete `SweBenchSmokeTask(Task[...])` subclass**

Mirrors the named-subclass pattern from PR 6 minif2f. Avoids the
parameterized-generic ``Task[X]`` discriminator that `import_component`
cannot resolve via ``getattr(module, "Task[X]")``.

- [ ] **Step 2: Override `build_instances` to return `Task`**

```python
class SweBenchSmokeTask(Task[SWEBenchTaskPayload]):
    ...

class SweBenchSmokeBenchmark(_SingleTaskSmokeBenchmark):
    ...

    def build_instances(self) -> Mapping[str, Sequence[Task[SWEBenchTaskPayload]]]:
        payload = SWEBenchTaskPayload.model_validate(self.task_payload)
        task = SweBenchSmokeTask(
            task_slug=self.task_slug,
            instance_key="default",
            description=self.task_description,
            evaluator_binding_keys=("default", "post-root"),
            task_payload=payload,
            evaluators=(
                SweBenchSmokeRubric(name="default"),
                SmokePostRootTimingRubric(name="post-root"),
            ),
        )
        return {"default": [task]}
```

- [ ] **Step 3: Migrate `SweBenchSmokeRubric` to pure Pydantic**

The smoke rubric currently has a custom `__init__(self, *, name, metadata=None)`
that's incompatible with Pydantic's `model_validate` (used by
`Evaluator.from_definition`). Replace with the
`Field(default_factory=tuple, exclude=True)` + `@model_validator(mode="after")`
pattern (see `ergon_builtins/benchmarks/minif2f/rubric.py` for the
exemplar). PR 6 did this for `MiniF2FSmokeRubric`; this step does the
same for the swebench counterpart.

## Task 6: Tests

- [ ] **Step 1: Definition JSON test**

Create `ergon_builtins/tests/unit/test_swebench_v2_definition.py`:

```python
import pytest
from ergon_core.api import persist_benchmark
from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SWEBenchVerifiedBenchmark,
)


@pytest.mark.asyncio
async def test_swebench_persists_object_bound_task_json(session_factory):
    benchmark = SWEBenchVerifiedBenchmark(
        name="swebench-smoke",
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
  ergon_core/tests/unit/runtime/test_definition_writer.py -q
```

Expected: pass; persisted JSON includes object-bound `_type`s for
worker, sandbox, and every evaluator entry.

## Task 7: Commit

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox.py \
        ergon_builtins/ergon_builtins/sandbox/_manager_backed.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/_tools.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py \
        ergon_builtins/ergon_builtins/benchmarks/swebench_verified/workers.py \
        ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox.py \
        ergon_builtins/ergon_builtins/benchmarks/README.md \
        ergon_builtins/tests/unit/test_swebench_v2_definition.py
git commit -m "feat(builtins): convert SWEBench to object-bound Task (PR 10a)"
```

Note: also includes `benchmarks/minif2f/sandbox.py` because PR 10a updates the MiniF2F sandbox to import the now-shared `ManagerBackedSandboxRuntime` from `sandbox/_manager_backed.py`.

## PR Ledger

Invariant landed: SWEBench builtin constructs object-bound task graphs;
shared `ManagerBackedSandboxRuntime` adapter exists for PR 10b/10c.

Bridge code introduced: `SWEBenchSandbox` wraps the legacy
`SWEBenchSandboxManager` via `ManagerBackedSandboxRuntime`; toolkit is
Pydantic-serializable.

Bridge code retired (partially):
- SWEBench tasks now carry `task.worker`/`task.sandbox` inline, so
  SWEBench runs no longer hit the `_legacy_worker_bridge` fallback that
  PR 5 Task 4b put on `worker_execute`.
- SWEBench tasks also carry `task.evaluators` inline, so SWEBench runs
  no longer hit the symmetric `_legacy_evaluator_bridge` fallback that
  PR 5 (restored post-cleanup) put on `evaluate_task_run`.
- Both fallbacks stay alive — they still serve researchrubrics, gdpeval,
  and the matching smoke fixtures until they migrate in PR 10b/10c.
  PR 11 deletes both bridges once every benchmark is on object-bound
  `Task`.

Old path still intentionally alive: `swebench_verified/sandbox_manager.py`,
registry registrations in `ergon_builtins/registry*.py`,
`_legacy_worker_bridge.py`, and `_legacy_evaluator_bridge.py` (the last
two are still required by researchrubrics, gdpeval, and any unmigrated
smoke fixtures).

Migrations: this PR adds **no Alembic migration** (the SWEBench changes
are code-only). The next free migration id is `aabbccdd0005`; reserve
it for PR 10b if/when needed.

Deletion gate: PR 11 deletes the manager file and registry registrations.
PR 10c's cross-cutting cleanup verifies migrated benchmarks no longer
import `ComponentRegistry`.

Tests added or updated: SWEBench definition JSON + reconstruction.

Modules owned by this PR: `swebench_verified/`, the shared sandbox
adapter, and the SWEBench toolkit.
