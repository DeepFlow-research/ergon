# PR 6 — MiniF2F V2 Vertical

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Convert one real builtin benchmark, MiniF2F, to the object-bound
v2 authoring shape end to end.

**Architecture:** Reuse existing MiniF2F sandbox/toolkit logic, but move the
sandbox kind into a `LeanSandbox(Sandbox)` class and have benchmark tasks
carry concrete worker/sandbox/evaluator objects.

**Tech Stack:** Pydantic workers, builtin benchmark factories, E2B-backed
sandbox bridge, pytest.

---

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/sandboxes/__init__.py
ergon_builtins/ergon_builtins/sandboxes/lean.py
ergon_builtins/ergon_builtins/toolkits/__init__.py
ergon_builtins/ergon_builtins/toolkits/minif2f.py
```

**Modify:**

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py
ergon_builtins/ergon_builtins/benchmarks/minif2f/worker_factory.py
ergon_builtins/ergon_builtins/benchmarks/minif2f/rubric.py
ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
ergon_builtins/tests/unit/
ergon_core/tests/unit/runtime/test_experiment_definition_service.py
```

## Current State

MiniF2F returns `TaskSpec` and relies on worker/sandbox registry binding:

```python
TaskSpec(
    task_slug="prove",
    instance_key="sample-1",
    description="Prove theorem sample-1.",
    evaluator_binding_keys=("default",),
)
```

## Target State For This PR

MiniF2F returns:

```python
Task(
    task_slug="prove",
    instance_key="sample-1",
    description="Prove theorem sample-1.",
    worker=ReActWorker(
        name="solver",
        model="openai:gpt-4o-mini",
        system_prompt="Write a Lean proof.",
        max_iterations=8,
        toolkit=MiniF2FToolkit(),
    ),
    sandbox=LeanSandbox(lean_version="4.7.0"),
    evaluators=(mini_f2f_rubric(),),
)
```

## Task 1: Add `LeanSandbox`

**Files:**

- Create: `ergon_builtins/ergon_builtins/sandboxes/lean.py`

- [ ] **Step 1: Implement class**

`BaseSandboxManager.create` returns an `AsyncSandbox` (E2B SDK) and stores
it keyed by `task_id` for later `get_sandbox(task_id)` access. The adapter
needs to remember `task_id` so every IO method can look the sandbox up.

```python
import inspect
from uuid import UUID, uuid4

from ergon_core.api.sandbox import Sandbox
from ergon_builtins.benchmarks.minif2f.sandbox_manager import (
    MiniF2FSandboxManager,
)


class LeanSandbox(Sandbox):
    """Lean 4 sandbox for MiniF2F. Wraps the legacy E2B manager during PR 6."""

    lean_version: str = "4.7.0"
    e2b_template: str = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"

    async def provision(self) -> None:
        manager = MiniF2FSandboxManager()
        sandbox_key = uuid4()
        await manager.create(task_id=sandbox_key, envs=self.env)
        live_sandbox = manager.get_sandbox(sandbox_key)
        if live_sandbox is None:
            raise RuntimeError(
                f"MiniF2FSandboxManager.create returned but no sandbox is "
                f"registered for task_id={sandbox_key}"
            )
        runtime = _ManagerBackedSandboxRuntime(
            manager=manager,
            sandbox=live_sandbox,
            sandbox_key=sandbox_key,
        )
        object.__setattr__(self, "_runtime", runtime)
```

The `task_id` here is a sandbox-cache key, not the `Task.task_id` — the
manager uses it as a dictionary key. PR 10 extracts this adapter into
`ergon_builtins/ergon_builtins/sandboxes/_manager_backed.py` for reuse.

- [ ] **Step 2: Add runtime adapter**

`BaseSandboxManager` exposes `create / get_sandbox / upload_file /
list_files / terminate`. It does **not** expose `run_command` or
`read_file` directly — those are E2B SDK methods on the `AsyncSandbox`
itself. The adapter goes through the live sandbox handle:

```python
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from ergon_core.api.sandbox.runtime import CommandResult


class _E2BSandboxHandle(Protocol):
    """Typed view over the parts of e2b's `AsyncSandbox` we depend on.

    The e2b SDK doesn't ship a Protocol we can import; we define one
    here at the boundary so the rest of the adapter stays typed.
    `sandbox_id`, `commands.run`, and `files.read|write` are stable
    parts of the e2b SDK surface circa 2026.
    """

    sandbox_id: str
    commands: "_E2BCommands"
    files: "_E2BFiles"


class _E2BCommands(Protocol):
    async def run(self, cmd: str, *, timeout: int | None = None): ...


class _E2BFiles(Protocol):
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, content: bytes) -> None: ...


class _ManagerBackedSandboxRuntime:
    """Adapter from BaseSandboxManager + AsyncSandbox to SandboxRuntime."""

    def __init__(
        self,
        *,
        manager,
        sandbox: _E2BSandboxHandle,
        sandbox_key: UUID,
    ) -> None:
        self._manager = manager
        self._sandbox = sandbox
        self._sandbox_key = sandbox_key
        # e2b's AsyncSandbox always carries `sandbox_id`; the Protocol
        # makes that contract explicit so no getattr fallback is needed.
        # If a non-conforming handle slips in, AttributeError surfaces
        # immediately rather than masquerading as a stringified UUID.
        self.sandbox_id: str = sandbox.sandbox_id

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        rendered = cmd if isinstance(cmd, str) else " ".join(cmd)
        result = await self._sandbox.commands.run(rendered, timeout=timeout)
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def write_file(self, path: str, content: bytes) -> None:
        # Manager.upload_file expects (task_id, local_path, sandbox_path).
        # We have bytes — use the underlying SDK directly for parity with
        # the v1 path. PR 10 normalizes this on the shared adapter.
        await self._sandbox.files.write(path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._sandbox.files.read(path)

    async def list_files(self, path: str) -> list[str]:
        return await self._manager.list_files(self._sandbox_key, path)

    async def close(self) -> None:
        await self._manager.terminate(self._sandbox_key, reason="completed")
```

The adapter deliberately calls `_sandbox.commands.run` and
`_sandbox.files.{read,write}` directly because `BaseSandboxManager` does
not expose those entry points. `list_files` and `terminate` go through
the manager so its caching/observability stays intact. If
`BaseSandboxManager` grows `run_command` / `read_file` between now and
PR 10, switch to those at that point.

## Task 2: Make ReActWorker And MiniF2FToolkit Serializable

**Files:**

- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Modify: `ergon_builtins/ergon_builtins/toolkits/minif2f.py`

`ReActWorker.toolkit` round-trips through the `_type` discriminator, so
both the worker AND the toolkit must be Pydantic BaseModels. The toolkit
holds **config**, not live runtime handles — its `tools(...)` method
constructs runtime tool objects lazily at execute time.

- [ ] **Step 1: Convert `MiniF2FToolkit` to Pydantic BaseModel**

In `ergon_builtins/ergon_builtins/toolkits/minif2f.py`:

```python
from pydantic import BaseModel, ConfigDict


class MiniF2FToolkit(BaseModel):
    """Serializable MiniF2F toolkit config.

    Carries only config (file paths, limits, flags). Runtime tool
    handles are built lazily via `tools(sandbox, task)`; they are not
    serializable and never round-trip through JSON.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    proof_output_path: str = "/workspace/final_output/proof.lean"
    lean_workspace: str = "/workspace/lean"
    max_tool_calls: int = 32

    def tools(self, sandbox, task):
        # Lazy import keeps runtime tool construction out of the
        # serialization path. The internal module builds AgentTool
        # instances bound to the live sandbox.
        from ergon_builtins.toolkits._minif2f_tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
```

Move any runtime tool construction (`AgentTool` instances bound to the
sandbox) into a sibling `_minif2f_tools.py` module. The toolkit
serializes; the tools never do.

- [ ] **Step 2: Convert `ReActWorker` constructor state to Pydantic fields**

Make `ReActWorker` inherit `Worker` once `Worker` becomes a Pydantic
model. Fields:

```python
name: str
model: str | None
system_prompt: str
max_iterations: int = 20
toolkit: MiniF2FToolkit | None = None
```

Runtime-only clients (LLM provider handle, http client) go into
`PrivateAttr`.

PR 10a / 10b / 10c each extend `ReActWorker.toolkit`'s type union to
include their toolkit, OR — once a third toolkit lands — replace the
union with a `Toolkit` protocol that requires `model_dump()` and
`tools(sandbox, task)`.

- [ ] **Step 3: Smoke test toolkit round-trip**

```python
def test_minif2f_toolkit_round_trips_through_json() -> None:
    tk = MiniF2FToolkit(max_tool_calls=16)
    serialized = tk.model_dump(mode="json")
    assert serialized["_type"].endswith(":MiniF2FToolkit")
    rebuilt = MiniF2FToolkit.model_validate(serialized)
    assert rebuilt.max_tool_calls == 16
```

## Task 3: Convert Benchmark Tasks

**Files:**

- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/worker_factory.py`

- [ ] **Step 1: Replace imports**

Replace:

```python
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, TaskSpec
```

with:

```python
from ergon_core.api import Benchmark, BenchmarkRequirements, Task
from ergon_builtins.sandboxes import LeanSandbox
from ergon_builtins.toolkits.minif2f import MiniF2FToolkit
```

- [ ] **Step 2: Replace `TaskSpec` construction**

Each task becomes:

```python
Task[MiniF2FTaskPayload](
    task_slug="prove",
    instance_key=instance_key,
    description=description,
    task_payload=payload,
    worker=make_minif2f_worker(),
    sandbox=LeanSandbox(),
    evaluators=(make_minif2f_rubric(),),
)
```

## Task 4: Tests

**Files:**

- Modify: `ergon_builtins/tests/unit/`
- Modify: `ergon_core/tests/unit/runtime/test_experiment_definition_service.py`

- [ ] **Step 1: Add definition JSON assertion**

Persist a MiniF2F experiment and assert the first task JSON includes:

```python
assert task_json["worker"]["_type"].endswith(":ReActWorker")
assert task_json["worker"]["toolkit"]["_type"].endswith(":MiniF2FToolkit")
assert task_json["sandbox"]["_type"].endswith(":LeanSandbox")
assert task_json["evaluators"], "evaluators must persist"
# Every evaluator entry must carry a `_type` discriminator so it can
# round-trip through Evaluator.from_definition / Rubric.from_definition.
assert all(
    ev.get("_type") for ev in task_json["evaluators"]
), "every evaluator entry must carry a `_type` discriminator"
assert "_legacy" not in task_json, (
    "MiniF2F is now object-bound; the _legacy bridge marker should be absent"
)
```

- [ ] **Step 2: Run focused tests**

```bash
uv run pytest ergon_builtins/tests/unit ergon_core/tests/unit/runtime/test_experiment_definition_service.py -q
```

## PR Ledger

Invariant landed: one builtin proves the v2 authoring vertical.

Bridge code introduced: manager-backed `LeanSandbox` runtime adapter.

Old path still intentionally alive: other builtins, registry, base sandbox
manager.

Deletion gate: PR 10 migrates all builtins; PR 11 deletes manager bridge.

Tests added or updated: MiniF2F definition JSON and builtin unit tests.

Modules owned by this PR: MiniF2F and builtin sandbox adapter.
