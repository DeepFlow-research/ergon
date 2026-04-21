---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/01_public_api.md#criterionruntime, docs/architecture/06_builtins.md#evaluator-criterion-and-rubric-layout]
supersedes: []
superseded_by: null
---

# RFC: Expand `CriterionRuntime` into a dependency-injection container

## Problem

`CriterionRuntime` is defined at
`ergon_core/ergon_core/api/criterion_runtime.py:48–63` as a seven-method
Protocol:

```python
class CriterionRuntime(Protocol):
    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...
```

The concrete implementation is `DefaultCriterionRuntime` at
`ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py:32`. The
Protocol covers sandbox access and one-shot LLM judging. Three gaps remain:

1. **No resource I/O.** Criteria that need to read worker-published blobs
   (`RunResource` rows) have no `read_resource(name)` or `list_resources()`
   accessor on the Protocol. They must open their own DB session, query
   `RunResource` by `(run_id, name)`, and read from the blob path on disk —
   bypassing the runtime entirely.

2. **No read-only DB session.** Criteria that query run state (prior attempts,
   sibling task results, task metadata) must call
   `ergon_core.core.persistence.shared.db.get_session()` directly. There is no
   `db_read_session()` on the Protocol, so the session-management contract is
   implicit and unchecked.

3. **No event-emission surface.** Agentic criteria that want to surface
   progress to the dashboard have no path to the `DashboardEmitter` at
   `ergon_core/ergon_core/core/dashboard/emitter.py:51`. The runtime does not
   expose an `event_sink()` accessor.

4. **Anti-pattern evidence.** The SWE-Bench criterion at
   `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py:66–78`
   defines `_spawn_eval_sandbox(run_id)` which instantiates
   `SWEBenchSandboxManager()` directly at line 72, allocates a fresh
   `sandbox_key` at line 73, calls `manager.create(...)` at line 74, and
   returns the new sandbox. Every SWE-bench eval invocation pays an extra
   sandbox allocation.

   Root cause: when `SWEBenchTestCriterion` was written, there was no way to
   pull worker-published artifacts via the runtime. The simplest available path
   was to bring up a fresh sandbox. Tracked as P2 bug
   `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md`, asserted
   (xfail) at `tests/state/test_criteria_do_not_spawn_sandboxes.py:19–32`.

   Closing the resource I/O gap removes the last legitimate reason a criterion
   would construct a sandbox manager itself. After this RFC, `_spawn_eval_sandbox`
   is replaced by `await runtime.ensure_sandbox()` plus
   `await runtime.read_resource(name)` for any worker-produced artifacts.

   Note: the bug report's proposed fix references `runtime.get_sandbox()`, but
   the RFC (§ Proposal below) explicitly rejects adding `get_sandbox()`.
   The bug-report fix is superseded by the `ensure_sandbox()` +
   `read_resource()` path.

## Proposal

Extend `CriterionRuntime` with four new methods, implement them on
`DefaultCriterionRuntime`, and migrate the swebench offender.

**Option chosen: extend the existing Protocol (Option A).**

The four new methods are:

```python
# ergon_core/ergon_core/api/criterion_runtime.py — additions

async def read_resource(self, name: str) -> bytes: ...
async def list_resources(self) -> list[RunResourceView]: ...
def db_read_session(self) -> Session: ...
def event_sink(self) -> SandboxEventSink: ...
```

`RunResourceView` is the frozen DTO at
`ergon_core/ergon_core/api/run_resource.py:22`.
`SandboxEventSink` is the Protocol at
`ergon_core/ergon_core/core/providers/sandbox/event_sink.py:7`.
`Session` is `sqlmodel.Session`.

`DefaultCriterionRuntime` is constructed with `run_id` and `task_id` from the
`EvaluationContext` already in scope at the call site
(`inngest_executor.py:73–76`). The `run_id` is used to scope resource and DB
queries; `task_id` is stored for tracing.

### What does NOT change

- The seven existing Protocol methods — signatures unchanged.
- `EvaluationContext` — no new fields.
- `CriterionContext` / `TaskEvaluationContext` — no changes.
- `InngestCriterionExecutor` constructor — only `DefaultCriterionRuntime`
  construction inside it changes.
- Alembic migrations — no schema change; `RunResource` table already exists.
- Criterion base class (`ergon_core/ergon_core/api/criterion.py`) — unchanged.

### Option B (rejected): separate agentic and non-agentic Protocols

Split into `CriterionRuntime` (sandbox/resource) and `AgentCriterionRuntime`
(adds `event_sink`). Rejected — every criterion benefits uniformly from
resource and DB access. A split doubles inheritance surface with no concrete
benefit until there is a criterion that truly cannot tolerate the extra
methods.

### Option C (rejected): add `get_sandbox()` accessor

An earlier draft proposed `get_sandbox() -> AsyncSandbox | None`. Rejected —
`ensure_sandbox()` already covers "provision or reconnect and hand back the
task sandbox." A separate raw accessor splits responsibility without benefit
and would expose the sandbox provider type across the Protocol boundary.

## Architecture overview

### Current data flow (swebench criterion)

```
inngest_executor.py
  └── InngestCriterionExecutor.execute_all()
        └── DefaultCriterionRuntime(context, sandbox_manager)
              └── criterion.evaluate(eval_ctx)         ← EvaluationContext.runtime set
                    └── _spawn_eval_sandbox(run_id)     ← ANTI-PATTERN
                          └── SWEBenchSandboxManager()  ← fresh sandbox manager
                                └── manager.create(...)  ← new sandbox allocation
```

### After this RFC

```
inngest_executor.py
  └── InngestCriterionExecutor.execute_all()
        └── DefaultCriterionRuntime(
              context=criterion_context,
              sandbox_manager=self.sandbox_manager,
              run_id=eval_ctx.run_id,          ← NEW
              task_id=eval_ctx.task_id,         ← NEW
            )
              └── criterion.evaluate(eval_ctx)
                    ├── runtime.ensure_sandbox()          ← reuses task sandbox
                    ├── runtime.read_resource("patch")    ← queries RunResource table
                    ├── runtime.list_resources()           ← lists run resources
                    ├── runtime.db_read_session()          ← read-only session
                    └── runtime.event_sink()               ← DashboardEmitterSandboxEventSink
```

### `DefaultCriterionRuntime.__init__` before / after

Before (line 38–50 of `criterion_runtime.py`):

```python
def __init__(
    self,
    context: CriterionContext,
    sandbox_manager: "BaseSandboxManager",
    llm_model: str = "gpt-4o",
    llm_max_tokens: int = 1024,
    llm_temperature: float = 0.0,
) -> None:
```

After:

```python
def __init__(
    self,
    context: CriterionContext,
    sandbox_manager: "BaseSandboxManager",
    run_id: UUID | None = None,
    task_id: UUID | None = None,
    llm_model: str = "gpt-4o",
    llm_max_tokens: int = 1024,
    llm_temperature: float = 0.0,
) -> None:
```

`run_id` defaults to `context.run_id` if `None` is passed; `task_id` is
optional and used only in trace attributes. Both are keyword-only in practice
(positional slots after `sandbox_manager` — callers that pass only
`context` and `sandbox_manager` are unaffected).

## Type / interface definitions

### Updated `CriterionRuntime` Protocol

```python
# ergon_core/ergon_core/api/criterion_runtime.py

"""Public Protocol for the criterion runtime + its small result DTOs.

``CriterionRuntime`` is the capabilities surface criteria use to interact
with the sandbox and LLM judge while they evaluate.  Lives in ``api/`` so
that ``EvaluationContext`` (also in ``api/``) can type it without dragging
in the core runtime package (which would cause a circular import).
"""

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel, Field
from sqlmodel import Session

T = TypeVar("T", bound=BaseModel)

if TYPE_CHECKING:
    from ergon_core.api.run_resource import RunResourceView
    from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink

__all__ = ["CommandResult", "CriterionRuntime", "SandboxResult"]


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)


class CommandResult(BaseModel):
    """Result from command execution in a sandbox."""

    stdout: str | None = Field(default=None)
    stderr: str | None = Field(default=None)
    exit_code: int | None = Field(default=None)


class CriterionRuntime(Protocol):
    """Execution surface injected into a ``Criterion`` at evaluation time.

    The runtime owns the sandbox lifecycle (create / reset timeout /
    cleanup) on behalf of the criterion and exposes a small set of
    primitives the criterion calls to gather evidence.  A criterion that
    doesn't need sandbox access or a judge simply ignores it.

    Surface-area constraint: this Protocol is narrowly scoped to sandbox
    lifecycle, resource I/O, and event emission.  It should not grow into
    a generic service locator.  ``call_llm_judge`` is the one method not
    strictly about I/O; if the Protocol keeps expanding it is a candidate
    for extraction into an ``LLMJudgeMixin``.
    """

    # ── sandbox lifecycle (existing) ──────────────────────────────────
    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...

    # ── resource I/O (new) ────────────────────────────────────────────
    async def read_resource(self, name: str) -> bytes: ...
    """Read a worker-published blob by name for this run.

    Queries ``run_resources`` for the latest row matching ``(run_id, name)``
    and reads the content-addressed blob from disk.

    Raises ``ResourceNotFoundError`` if no row matches.
    Raises ``OSError`` if the blob file is missing or unreadable.
    """

    async def list_resources(self) -> list["RunResourceView"]: ...
    """Return all ``RunResourceView`` DTOs for this run, newest first."""

    # ── DB access (new) ───────────────────────────────────────────────
    def db_read_session(self) -> Session: ...
    """Return a ``sqlmodel.Session`` for read-only queries.

    The caller owns the session lifecycle (open / close).  Use as a
    context manager:  ``with runtime.db_read_session() as s: ...``
    Mutating writes via this session violate the contract but are not
    enforced at runtime in v1.
    """

    # ── event emission (new) ──────────────────────────────────────────
    def event_sink(self) -> "SandboxEventSink": ...
    """Return the ``SandboxEventSink`` wired to the dashboard emitter.

    Agentic criteria may call ``await sink.sandbox_command(...)`` to stream
    progress events to the real-time dashboard.  Returns a ``NoopSandboxEventSink``
    if dashboard streaming is disabled.
    """
```

## Full implementations

### `ergon_core/ergon_core/api/criterion_runtime.py` (complete updated file)

```python
# ergon_core/ergon_core/api/criterion_runtime.py

"""Public Protocol for the criterion runtime + its small result DTOs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

if TYPE_CHECKING:
    from sqlmodel import Session

    from ergon_core.api.run_resource import RunResourceView
    from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink

__all__ = ["CommandResult", "CriterionRuntime", "SandboxResult"]


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str] = Field(
        default_factory=list,
        description="Captured stdout lines from the sandbox process.",
    )
    stderr: list[str] = Field(
        default_factory=list,
        description="Captured stderr lines from the sandbox process.",
    )


class CommandResult(BaseModel):
    """Result from command execution in a sandbox."""

    stdout: str | None = Field(
        default=None,
        description="Captured stdout; ``None`` if the command never produced any.",
    )
    stderr: str | None = Field(
        default=None,
        description="Captured stderr; ``None`` if the command never produced any.",
    )
    exit_code: int | None = Field(
        default=None,
        description="Process exit code; ``None`` if the command could not be started.",
    )


class CriterionRuntime(Protocol):
    """Execution surface injected into a ``Criterion`` at evaluation time.

    The runtime owns the sandbox lifecycle (create / reset timeout /
    cleanup) on behalf of the criterion and exposes a small set of
    primitives the criterion calls to gather evidence.  A criterion that
    doesn't need sandbox access or a judge simply ignores it.

    Surface-area constraint: this Protocol is narrowly scoped to sandbox
    lifecycle, resource I/O, and event emission.  It should not grow into
    a generic service locator.
    """

    # ── sandbox lifecycle ─────────────────────────────────────────────
    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...

    # ── resource I/O ──────────────────────────────────────────────────
    async def read_resource(self, name: str) -> bytes: ...
    async def list_resources(self) -> list[RunResourceView]: ...

    # ── DB access ─────────────────────────────────────────────────────
    def db_read_session(self) -> Session: ...

    # ── event emission ────────────────────────────────────────────────
    def event_sink(self) -> SandboxEventSink: ...
```

### `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` (complete updated file)

```python
# ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py

"""Default concrete implementation of ``CriterionRuntime``."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from ergon_core.api.criterion_runtime import (
    CommandResult,
    CriterionRuntime,
    SandboxResult,
)
from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.providers.sandbox.event_sink import (
    DashboardEmitterSandboxEventSink,
    NoopSandboxEventSink,
    SandboxEventSink,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext
from ergon_core.core.settings import settings
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlmodel import Session, select

if TYPE_CHECKING:
    from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

__all__ = ["CriterionRuntime", "DefaultCriterionRuntime", "ResourceNotFoundError"]


class ResourceNotFoundError(LookupError):
    """Raised by ``read_resource`` when no ``RunResource`` row matches the name."""


class DefaultCriterionRuntime:
    """Real criterion runtime backed by sandbox manager + OpenAI + DB.

    Parameters
    ----------
    context:
        ``CriterionContext`` passed by the executor.  ``context.run_id`` is
        the default ``run_id`` for resource and DB queries if ``run_id`` is
        not provided explicitly.
    sandbox_manager:
        The ``BaseSandboxManager`` that owns the task sandbox.
    run_id:
        Explicit run UUID for resource/DB scoping.  Defaults to
        ``context.run_id`` if ``None``.
    task_id:
        Task UUID used in trace attributes; optional.
    llm_model:
        OpenAI model name for ``call_llm_judge``.
    llm_max_tokens:
        Token limit for judge responses.
    llm_temperature:
        Sampling temperature for judge calls.
    event_sink:
        Pre-constructed ``SandboxEventSink``.  If ``None`` a
        ``NoopSandboxEventSink`` is used.
    """

    def __init__(
        self,
        context: CriterionContext,
        sandbox_manager: BaseSandboxManager,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        llm_model: str = "gpt-4o",
        llm_max_tokens: int = 1024,
        llm_temperature: float = 0.0,
        event_sink: SandboxEventSink | None = None,
    ) -> None:
        self.context = context
        self.sandbox_manager: BaseSandboxManager = sandbox_manager
        self._run_id: UUID = run_id if run_id is not None else context.run_id
        self._task_id: UUID | None = task_id
        self._owns_sandbox = False
        self._llm_model = llm_model
        self._llm_max_tokens = llm_max_tokens
        self._llm_temperature = llm_temperature
        self._event_sink: SandboxEventSink = event_sink or NoopSandboxEventSink()

    # ── sandbox lifecycle ─────────────────────────────────────────────

    async def ensure_sandbox(self) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            await self.sandbox_manager.create(
                self._run_id,
                run_id=self._run_id,
                timeout_minutes=30,
            )
            self._owns_sandbox = True
            return
        await self.sandbox_manager.reset_timeout(self._run_id, timeout_minutes=30)

    async def upload_files(self, files: list[dict]) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        for resource in files:
            name = resource.get("name", "unknown")
            sandbox_path = f"/evaluation/{name}"
            content = resource.get("content", b"")
            if isinstance(content, str):
                content = content.encode("utf-8")
            try:
                await sandbox.files.write(sandbox_path, content)
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                logger.warning("Failed to upload %s: %s", name, exc)

    async def write_file(self, path: str, content: bytes) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        try:
            result = await sandbox.commands.run(command, timeout=timeout)
            return CommandResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return CommandResult(stdout="", stderr=str(exc), exit_code=1)

    async def execute_code(self, code: str) -> SandboxResult:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created")
        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
            return SandboxResult(
                stdout=list(execution.logs.stdout),
                stderr=list(execution.logs.stderr),
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            error_msg = str(exc)
            if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                raise RuntimeError(
                    f"Sandbox execution failed (likely timeout): {error_msg}. "
                    "Code criterion may have taken too long (>30s)."
                ) from exc
            raise

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.beta.chat.completions.parse(
            model=self._llm_model,
            messages=messages,
            max_tokens=self._llm_max_tokens,
            temperature=self._llm_temperature,
            response_format=response_type,
        )
        message = response.choices[0].message
        if message.parsed is None:
            raise ValueError("No parsed response from LLM judge")
        return message.parsed

    async def cleanup(self) -> None:
        if self._owns_sandbox:
            await self.sandbox_manager.terminate(self._run_id)
            self._owns_sandbox = False

    # ── resource I/O (new) ────────────────────────────────────────────

    async def read_resource(self, name: str) -> bytes:
        """Read the latest worker-published blob for ``name`` in this run.

        Queries ``run_resources`` for the most-recently-created row matching
        ``(run_id, name)``, then reads bytes from ``file_path`` on disk.

        Raises
        ------
        ResourceNotFoundError
            No ``run_resources`` row matches ``(run_id, name)``.
        OSError
            The blob file is missing or unreadable.
        """
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .where(RunResource.name == name)
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]
                .limit(1)
            )
            row = session.exec(stmt).first()

        if row is None:
            raise ResourceNotFoundError(
                f"No run_resource named {name!r} for run {self._run_id}"
            )

        return Path(row.file_path).read_bytes()

    async def list_resources(self) -> list[RunResourceView]:
        """Return all ``RunResourceView`` DTOs for this run, newest first."""
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]
            )
            rows = list(session.exec(stmt).all())
        return [RunResourceView.from_row(r) for r in rows]

    # ── DB access (new) ───────────────────────────────────────────────

    def db_read_session(self) -> Session:
        """Return a ``sqlmodel.Session`` for read-only queries.

        The caller owns the session lifecycle.  Use as a context manager:

            with runtime.db_read_session() as s:
                result = s.exec(select(RunRecord).where(...)).first()

        Mutating writes via this session violate the intent but are not
        blocked at runtime in v1.
        """
        return get_session()

    # ── event emission (new) ──────────────────────────────────────────

    def event_sink(self) -> SandboxEventSink:
        """Return the ``SandboxEventSink`` wired to the dashboard emitter."""
        return self._event_sink
```

### Migrated `swebench_verified/criterion.py` (Task 0 — `_spawn_eval_sandbox` removed)

Only the changed region is shown; the rest of the file is unchanged.

```python
# ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py
# Task 0 diff target: remove _spawn_eval_sandbox, use runtime.ensure_sandbox()

# REMOVED imports:
#   from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import SWEBenchSandboxManager
#   import uuid  (no longer needed for sandbox_key allocation)

# REMOVED function:
#   async def _spawn_eval_sandbox(run_id: UUID) -> Any: ...

# CHANGED in SWEBenchTestCriterion.evaluate():

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        worker = context.worker_result
        patch_text = (worker.artifacts or {}).get("patch") or worker.output or ""
        if not patch_text.strip():
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="Empty patch — agent did not produce any edits.",
                metadata={},
            )

        payload = context.task.task_payload
        row = _payload_to_swebench_row(payload)
        spec = make_test_spec(row)

        if context.runtime is None:
            raise RuntimeError(
                "SWEBenchTestCriterion requires a CriterionRuntime; "
                "none was injected into EvaluationContext."
            )

        await context.runtime.ensure_sandbox()
        sandbox = context.runtime.sandbox_manager.get_sandbox(context.run_id)
        if sandbox is None:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback="Sandbox unavailable after ensure_sandbox().",
                metadata={"error": "sandbox_unavailable"},
            )

        try:
            return await self._run_and_grade(
                sandbox=sandbox, spec=spec, payload=payload, patch_text=patch_text
            )
        finally:
            # Runtime owns cleanup; do not kill here.
            pass
```

**Note:** `context.runtime.sandbox_manager` is accessed directly because
`CriterionRuntime` does not expose the raw sandbox object — by design. This
is an acceptable internal coupling within `ergon_builtins` because
`DefaultCriterionRuntime` is the only concrete runtime in production and
`sandbox_manager` is a public attribute. If the Protocol later adds a
`run_command`-based harness path, this coupling can be removed.

Alternatively: replace the `sandbox.commands.run(...)` calls in
`_run_and_grade` with `await context.runtime.run_command(...)` calls. That
would make `_run_and_grade` fully Protocol-bound. That migration is Phase 3
scope.

### Updated `InngestCriterionExecutor` (construction site)

```python
# ergon_core/ergon_core/core/runtime/evaluation/inngest_executor.py
# Changed region only — construct DefaultCriterionRuntime with run_id + task_id

                runtime = DefaultCriterionRuntime(
                    context=criterion_context,
                    sandbox_manager=self.sandbox_manager,
                    run_id=task_context.run_id,   # NEW
                    task_id=self.task_id,           # NEW
                )
```

`self.task_id` is already stored on `InngestCriterionExecutor` at line 37
(`self.task_id = task_id`). No other changes to that file.

## Exact diffs

### `ergon_core/ergon_core/api/criterion_runtime.py`

```diff
-from typing import Protocol, TypeVar
+from __future__ import annotations
+
+from typing import TYPE_CHECKING, Protocol, TypeVar

-from pydantic import BaseModel, Field
+from pydantic import BaseModel, Field

 T = TypeVar("T", bound=BaseModel)

-__all__ = ["CommandResult", "CriterionRuntime", "SandboxResult"]
+if TYPE_CHECKING:
+    from sqlmodel import Session
+
+    from ergon_core.api.run_resource import RunResourceView
+    from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink
+
+__all__ = ["CommandResult", "CriterionRuntime", "SandboxResult"]

 class CriterionRuntime(Protocol):
     """..."""
+    """
+    Surface-area constraint: narrowly scoped to sandbox lifecycle,
+    resource I/O, and event emission.
+    """

     async def ensure_sandbox(self) -> None: ...
     async def upload_files(self, files: list[dict]) -> None: ...
     async def write_file(self, path: str, content: bytes) -> None: ...
     async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
     async def execute_code(self, code: str) -> SandboxResult: ...
     async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
     async def cleanup(self) -> None: ...
+
+    async def read_resource(self, name: str) -> bytes: ...
+    async def list_resources(self) -> list[RunResourceView]: ...
+    def db_read_session(self) -> Session: ...
+    def event_sink(self) -> SandboxEventSink: ...
```

### `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`

```diff
+from __future__ import annotations
+
 import logging
+from pathlib import Path
 from typing import TYPE_CHECKING, TypeVar
-from uuid import UUID
+from uuid import UUID

+from ergon_core.api.run_resource import RunResourceView
+from ergon_core.core.persistence.shared.db import get_session
+from ergon_core.core.persistence.telemetry.models import RunResource
+from ergon_core.core.providers.sandbox.event_sink import (
+    DashboardEmitterSandboxEventSink,
+    NoopSandboxEventSink,
+    SandboxEventSink,
+)
 from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext
+from sqlmodel import Session, select

-__all__ = ["CriterionRuntime", "DefaultCriterionRuntime"]
+__all__ = ["CriterionRuntime", "DefaultCriterionRuntime", "ResourceNotFoundError"]
+
+
+class ResourceNotFoundError(LookupError):
+    """Raised by ``read_resource`` when no ``RunResource`` row matches the name."""


 class DefaultCriterionRuntime:
     def __init__(
         self,
         context: CriterionContext,
         sandbox_manager: "BaseSandboxManager",
+        run_id: UUID | None = None,
+        task_id: UUID | None = None,
         llm_model: str = "gpt-4o",
         llm_max_tokens: int = 1024,
         llm_temperature: float = 0.0,
+        event_sink: SandboxEventSink | None = None,
     ) -> None:
         self.context = context
         self.sandbox_manager: BaseSandboxManager = sandbox_manager
+        self._run_id: UUID = run_id if run_id is not None else context.run_id
+        self._task_id: UUID | None = task_id
         self._owns_sandbox = False
         self._llm_model = llm_model
         self._llm_max_tokens = llm_max_tokens
         self._llm_temperature = llm_temperature
+        self._event_sink: SandboxEventSink = event_sink or NoopSandboxEventSink()

-    async def ensure_sandbox(self) -> None:
-        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
+    async def ensure_sandbox(self) -> None:
+        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
         if sandbox is None:
             await self.sandbox_manager.create(
-                self.context.run_id,
-                run_id=self.context.run_id,
+                self._run_id,
+                run_id=self._run_id,
                 timeout_minutes=30,
             )
             ...
-        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)
+        await self.sandbox_manager.reset_timeout(self._run_id, timeout_minutes=30)

-    # [upload_files, write_file, run_command, execute_code: same change self.context.run_id → self._run_id]
+    # ... [all get_sandbox/reset_timeout calls updated analogously]

-    async def cleanup(self) -> None:
-        if self._owns_sandbox:
-            await self.sandbox_manager.terminate(self.context.run_id)
+    async def cleanup(self) -> None:
+        if self._owns_sandbox:
+            await self.sandbox_manager.terminate(self._run_id)
             self._owns_sandbox = False

+    async def read_resource(self, name: str) -> bytes:
+        with get_session() as session:
+            stmt = (
+                select(RunResource)
+                .where(RunResource.run_id == self._run_id)
+                .where(RunResource.name == name)
+                .order_by(RunResource.created_at.desc())
+                .limit(1)
+            )
+            row = session.exec(stmt).first()
+        if row is None:
+            raise ResourceNotFoundError(
+                f"No run_resource named {name!r} for run {self._run_id}"
+            )
+        return Path(row.file_path).read_bytes()
+
+    async def list_resources(self) -> list[RunResourceView]:
+        with get_session() as session:
+            stmt = (
+                select(RunResource)
+                .where(RunResource.run_id == self._run_id)
+                .order_by(RunResource.created_at.desc())
+            )
+            rows = list(session.exec(stmt).all())
+        return [RunResourceView.from_row(r) for r in rows]
+
+    def db_read_session(self) -> Session:
+        return get_session()
+
+    def event_sink(self) -> SandboxEventSink:
+        return self._event_sink
```

### `ergon_core/ergon_core/core/runtime/evaluation/inngest_executor.py`

```diff
                 runtime = DefaultCriterionRuntime(
                     context=criterion_context,
                     sandbox_manager=self.sandbox_manager,
+                    run_id=task_context.run_id,
+                    task_id=self.task_id,
                 )
```

### `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`

```diff
-import uuid
 import logging
 import shlex
 import tempfile
+from pathlib import Path
 from typing import Any, ClassVar
 from uuid import UUID

-from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
-    SWEBenchSandboxManager,
-)
 from ergon_builtins.workers.baselines.swebench_worker import _payload_to_swebench_row

-async def _spawn_eval_sandbox(run_id: UUID) -> Any:
-    manager = SWEBenchSandboxManager()
-    sandbox_key = uuid.uuid4()
-    await manager.create(sandbox_key=sandbox_key, run_id=run_id)
-    sandbox = manager.get_sandbox(sandbox_key)
-    if sandbox is None:
-        raise RuntimeError("Failed to acquire eval sandbox after create()")
-    return sandbox
-
     async def evaluate(self, context: EvaluationContext) -> CriterionResult:
         ...
-        sandbox = await _spawn_eval_sandbox(context.run_id)
-        try:
-            return await self._run_and_grade(...)
-        finally:
-            await _safe_kill(sandbox)
+        if context.runtime is None:
+            raise RuntimeError(
+                "SWEBenchTestCriterion requires a CriterionRuntime; "
+                "none was injected into EvaluationContext."
+            )
+        await context.runtime.ensure_sandbox()
+        sandbox = context.runtime.sandbox_manager.get_sandbox(context.run_id)
+        if sandbox is None:
+            return CriterionResult(
+                name=self.name, score=0.0, passed=False, weight=self.weight,
+                feedback="Sandbox unavailable after ensure_sandbox().",
+                metadata={"error": "sandbox_unavailable"},
+            )
+        return await self._run_and_grade(
+            sandbox=sandbox, spec=spec, payload=payload, patch_text=patch_text
+        )

-async def _safe_kill(sandbox: Any) -> None: ...   # removed — runtime owns cleanup
```

### `tests/state/test_criteria_do_not_spawn_sandboxes.py`

```diff
-@pytest.mark.xfail(
-    reason=(
-        "swebench criterion still spawns its own sandbox; tracked in "
-        "docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md"
-    ),
-    strict=False,
-)
 def test_criteria_do_not_instantiate_sandbox_managers() -> None:
     offenders: list[str] = []
     for path in CRITERION_DIR.rglob("criterion.py"):
         content = path.read_text()
         if SANDBOX_MANAGER_PATTERN in content:
             offenders.append(str(path))
     assert not offenders, f"Criterion files directly instantiate SandboxManager: {offenders}"
```

## Package structure

No new packages are introduced. All changes are modifications within existing
packages. Updated `__all__` exports:

`ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`:

```python
__all__ = ["CriterionRuntime", "DefaultCriterionRuntime", "ResourceNotFoundError"]
```

## Implementation order

Phased into two PRs.

### PR 1 — Protocol + `DefaultCriterionRuntime` extension (additive, no criterion changes)

| Step | What | Files touched |
|---|---|---|
| 1 | Add `read_resource`, `list_resources`, `db_read_session`, `event_sink` signatures to `CriterionRuntime` Protocol | MODIFY `ergon_core/ergon_core/api/criterion_runtime.py` |
| 2 | Add `ResourceNotFoundError` to `criterion_runtime.py`; add `run_id`, `task_id`, `event_sink` params to `DefaultCriterionRuntime.__init__`; migrate all `self.context.run_id` → `self._run_id` calls | MODIFY `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` |
| 3 | Pass `run_id=task_context.run_id`, `task_id=self.task_id` at `DefaultCriterionRuntime` construction | MODIFY `ergon_core/ergon_core/core/runtime/evaluation/inngest_executor.py` |
| 4 | Implement `read_resource` + `list_resources` (DB query + blob read) on `DefaultCriterionRuntime` | MODIFY `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` |
| 5 | Implement `db_read_session` (returns `get_session()`) | MODIFY `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` |
| 6 | Implement `event_sink` (returns stored `_event_sink`); wire `DashboardEmitterSandboxEventSink` in executor | MODIFY `criterion_runtime.py`, MODIFY `inngest_executor.py` |
| 7 | Unit tests for all four new methods | ADD `tests/unit/test_criterion_runtime_di.py` |

### PR 2 — Task 0: swebench migration + xfail removal

| Step | What | Files touched |
|---|---|---|
| 8 | Remove `_spawn_eval_sandbox`, remove `SWEBenchSandboxManager` import, replace criterion body with `runtime.ensure_sandbox()` path | MODIFY `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` |
| 9 | Remove `_safe_kill` (no longer needed — runtime owns sandbox cleanup) | MODIFY `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` |
| 10 | Remove `@pytest.mark.xfail` from state test | MODIFY `tests/state/test_criteria_do_not_spawn_sandboxes.py` |
| 11 | Integration test: `SWEBenchTestCriterion.evaluate` with a mock runtime, assert no `SWEBenchSandboxManager` instantiation | ADD `tests/unit/test_swebench_criterion_no_sandbox.py` |
| 12 | Close bug `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md` — move to `docs/bugs/fixed/` with `fixed_pr` set | MOVE (out of scope for this RFC; done when PR 2 merges) |

### PR 3 — Phase 3 audit sweep (future, not blocked)

Walk every `Criterion` subclass under `ergon_builtins/`; convert ad-hoc DB
reads, `RunResource` queries, and emitter access to the new Protocol methods.
Estimated scope: single-digit files. Not required for this RFC to be accepted.

## File map

### MODIFY

| File | Change |
|---|---|
| `ergon_core/ergon_core/api/criterion_runtime.py` | Add 4 method signatures; add `TYPE_CHECKING` imports for `RunResourceView`, `SandboxEventSink`, `Session`; add docstring note on surface constraint |
| `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py` | Add `ResourceNotFoundError`; add `run_id`, `task_id`, `event_sink` params to `__init__`; migrate `self.context.run_id` → `self._run_id` throughout; implement `read_resource`, `list_resources`, `db_read_session`, `event_sink`; update `__all__` |
| `ergon_core/ergon_core/core/runtime/evaluation/inngest_executor.py` | Pass `run_id=task_context.run_id`, `task_id=self.task_id` to `DefaultCriterionRuntime` at line 73 |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py` | Remove `_spawn_eval_sandbox`, `_safe_kill`, `SWEBenchSandboxManager` import, `uuid` import; replace `evaluate` body with `runtime.ensure_sandbox()` path |
| `tests/state/test_criteria_do_not_spawn_sandboxes.py` | Remove `@pytest.mark.xfail` decorator (lines 19–25) |

### ADD

| File | Purpose |
|---|---|
| `tests/unit/test_criterion_runtime_di.py` | Unit tests: `read_resource` (found / not-found), `list_resources`, `db_read_session`, `event_sink` on `DefaultCriterionRuntime` |
| `tests/unit/test_swebench_criterion_no_sandbox.py` | Integration test: `SWEBenchTestCriterion.evaluate` with mock runtime; asserts `SWEBenchSandboxManager` never constructed |

## Testing approach

### Unit tests — `tests/unit/test_criterion_runtime_di.py`

```python
# tests/unit/test_criterion_runtime_di.py

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.runtime.evaluation.criterion_runtime import (
    DefaultCriterionRuntime,
    ResourceNotFoundError,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext


def _make_runtime(**overrides: Any) -> DefaultCriterionRuntime:
    context = CriterionContext(run_id=uuid4())
    sandbox_manager = MagicMock()
    kwargs: dict[str, Any] = {
        "context": context,
        "sandbox_manager": sandbox_manager,
    }
    kwargs.update(overrides)
    return DefaultCriterionRuntime(**kwargs)


class TestReadResource:
    def test_found_reads_blob(self, tmp_path: Path) -> None:
        """read_resource returns bytes from file_path on disk."""
        blob = tmp_path / "abc"
        blob.write_bytes(b"hello-world")

        from ergon_core.core.persistence.telemetry.models import RunResource
        from datetime import datetime, UTC

        run_id = uuid4()
        row = MagicMock(spec=RunResource)
        row.file_path = str(blob)
        row.run_id = run_id
        row.name = "patch"

        runtime = _make_runtime(run_id=run_id)

        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session"
        ) as mock_sess:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.exec.return_value.first.return_value = row
            mock_sess.return_value = mock_ctx

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                runtime.read_resource("patch")
            )

        assert result == b"hello-world"

    def test_not_found_raises(self) -> None:
        """read_resource raises ResourceNotFoundError when no row matches."""
        runtime = _make_runtime()

        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session"
        ) as mock_sess:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.exec.return_value.first.return_value = None
            mock_sess.return_value = mock_ctx

            import asyncio
            with pytest.raises(ResourceNotFoundError, match="no_such_resource"):
                asyncio.get_event_loop().run_until_complete(
                    runtime.read_resource("no_such_resource")
                )


class TestListResources:
    def test_returns_dtos_newest_first(self) -> None:
        """list_resources maps ORM rows to RunResourceView DTOs."""
        from ergon_core.api.run_resource import RunResourceView

        runtime = _make_runtime()
        mock_row = MagicMock()

        with (
            patch(
                "ergon_core.core.runtime.evaluation.criterion_runtime.get_session"
            ) as mock_sess,
            patch.object(RunResourceView, "from_row", return_value=MagicMock()) as mock_from_row,
        ):
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.exec.return_value.all.return_value = [mock_row]
            mock_sess.return_value = mock_ctx

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(runtime.list_resources())

        assert len(result) == 1
        mock_from_row.assert_called_once_with(mock_row)


class TestDbReadSession:
    def test_returns_session(self) -> None:
        """db_read_session returns a sqlmodel Session."""
        from sqlmodel import Session

        runtime = _make_runtime()
        with patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session"
        ) as mock_get:
            mock_get.return_value = MagicMock(spec=Session)
            sess = runtime.db_read_session()
        assert sess is mock_get.return_value


class TestEventSink:
    def test_returns_noop_by_default(self) -> None:
        from ergon_core.core.providers.sandbox.event_sink import NoopSandboxEventSink

        runtime = _make_runtime()
        assert isinstance(runtime.event_sink(), NoopSandboxEventSink)

    def test_returns_injected_sink(self) -> None:
        from ergon_core.core.providers.sandbox.event_sink import DashboardEmitterSandboxEventSink

        emitter = MagicMock()
        sink = DashboardEmitterSandboxEventSink(emitter)
        runtime = _make_runtime(event_sink=sink)
        assert runtime.event_sink() is sink


class TestRunIdResolution:
    def test_explicit_run_id_overrides_context(self) -> None:
        context = CriterionContext(run_id=uuid4())
        explicit_id = uuid4()
        runtime = DefaultCriterionRuntime(
            context=context,
            sandbox_manager=MagicMock(),
            run_id=explicit_id,
        )
        assert runtime._run_id == explicit_id

    def test_default_falls_back_to_context(self) -> None:
        context = CriterionContext(run_id=uuid4())
        runtime = DefaultCriterionRuntime(
            context=context,
            sandbox_manager=MagicMock(),
        )
        assert runtime._run_id == context.run_id
```

### Unit test — `tests/unit/test_swebench_criterion_no_sandbox.py`

```python
# tests/unit/test_swebench_criterion_no_sandbox.py

"""Verify SWEBenchTestCriterion no longer constructs SWEBenchSandboxManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.criterion import SWEBenchTestCriterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask


@pytest.mark.asyncio
async def test_evaluate_uses_runtime_ensure_sandbox() -> None:
    """After Task 0: criterion calls runtime.ensure_sandbox(), not SWEBenchSandboxManager."""
    criterion = SWEBenchTestCriterion()

    mock_sandbox = MagicMock()
    mock_sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout=""))
    mock_sandbox.files.write = AsyncMock()

    mock_runtime = MagicMock()
    mock_runtime.ensure_sandbox = AsyncMock()
    mock_runtime.sandbox_manager.get_sandbox.return_value = mock_sandbox

    context = EvaluationContext(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=BenchmarkTask(
            task_key="swe-001",
            instance_key="inst-001",
            description="fix the bug",
            task_payload={
                "instance_id": "swe-001",
                "test_patch": "",
                "base_commit": "abc123",
            },
        ),
        worker_result=WorkerOutput(output="diff --git a/foo.py b/foo.py\n+pass"),
        sandbox_id="sbx-test",
        runtime=mock_runtime,
    )

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec"
    ) as mock_spec, patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.get_eval_report"
    ) as mock_report:
        mock_spec.return_value = MagicMock(
            install_repo_script="echo ok",
            eval_script="echo ok",
        )
        mock_report.return_value = {
            "swe-001": {"resolved": True, "tests_status": {}}
        }
        await criterion.evaluate(context)

    mock_runtime.ensure_sandbox.assert_awaited_once()

    # Confirm SWEBenchSandboxManager was NOT instantiated.
    import ergon_builtins.benchmarks.swebench_verified.criterion as m
    assert not hasattr(m, "_spawn_eval_sandbox"), (
        "_spawn_eval_sandbox must be removed after Task 0"
    )
```

### State test (after xfail removal) — existing file

`tests/state/test_criteria_do_not_spawn_sandboxes.py` — unchanged except
removal of the `@pytest.mark.xfail` decorator. After Task 0 merges, the test
passes unconditionally and serves as a hard lint-style enforcement that
no criterion re-introduces direct sandbox construction.

## Trace / observability impact

### Existing span unchanged

`InngestCriterionExecutor` emits a `"evaluation.criterion"` span per criterion
at `inngest_executor.py:101–126`. No new span attributes are added by this RFC.

### New span attribute: `resource_reads`

When `read_resource` is called, add an INFO log with resource name and size:

```python
logger.info(
    "criterion read_resource run_id=%s name=%s size_bytes=%d",
    self._run_id,
    name,
    len(result),
)
```

This is a log, not a span attribute mutation, so no trace-schema migration is
required. If observability for resource reads becomes important, a counter
metric or span event can be added in a follow-up.

### No dashboard event from resource reads

`event_sink()` is surfaced to criteria for progress streaming (e.g.
`sandbox_command` events during agentic evaluation). The runtime itself does
not emit events on `read_resource` / `list_resources` calls — those are
transparent to the dashboard.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `read_resource` reads a stale or incomplete blob if two tasks publish the same name | Criterion gets wrong data | Query orders by `created_at DESC`, returns latest row. Document that name collisions across task executions are caller's responsibility. |
| `db_read_session()` used for writes (convention not enforced) | Unintended DB mutations inside criterion | Add "read-only" to docstring and naming; v2 can enforce via a read-only engine URL or a wrapper that raises on `session.add()`. |
| `context.runtime.sandbox_manager` accessed in swebench criterion (internal coupling) | Breaks if `DefaultCriterionRuntime.sandbox_manager` is renamed | Attribute is public in `DefaultCriterionRuntime`; rename would be caught by `ty`. Long-term: replace `sandbox.commands.run(...)` calls with `runtime.run_command(...)`. |
| `_spawn_eval_sandbox` removal breaks a criterion caller that was not identified | `SWEBenchTestCriterion.evaluate` fails with `AttributeError` | `grep` confirms `_spawn_eval_sandbox` is only called from `evaluate` at `criterion.py:156`; one callsite. |
| `NoopSandboxEventSink` injected at construction but criterion calls `await sink.sandbox_command(...)` synchronously | `NoopSandboxEventSink` is async-compatible — all methods are `async def` at `event_sink.py:11–31`. No risk. | Already handled. |
| Protocol structural compliance check misses the four new methods for existing mock runtimes in tests | Tests silently pass with incomplete mocks | Add a `TestCriterionRuntimeProtocolCompliance` test class that instantiates a `MagicMock(spec=CriterionRuntime)` and asserts all eleven methods exist. |

## Invariants affected

### `docs/architecture/01_public_api.md#criterionruntime`

Current text (lines 48–54):

> **`CriterionRuntime`** — Protocol. The execution context an agentic
> criterion uses to reach into its environment. **Surface-area constraint:**
> this Protocol is narrowly scoped to sandbox lifecycle and resource I/O; it
> should not grow into a generic service locator. The one current method that
> is not about sandbox/I/O is a candidate for extraction if the surface
> continues to accumulate capabilities. Expansion is in flight — see
> follow-ups.

After this RFC: update to reflect seven existing + four new methods. Surface
now includes sandbox lifecycle (7 methods), resource I/O (`read_resource`,
`list_resources`), DB read access (`db_read_session`), and event emission
(`event_sink`). Follow-up remains: if the surface keeps growing,
`call_llm_judge` is a candidate for extraction into `LLMJudgeMixin`.

Code-map table: add `ResourceNotFoundError | ergon_core/core/runtime/evaluation/criterion_runtime.py`.

### `docs/architecture/01_public_api.md` — anti-patterns

Current text (lines 213–214):

> - **Criteria that allocate their own sandbox.** Agentic criteria must run in
>   the task's existing sandbox via the `CriterionRuntime` seam. Current
>   offender: `ergon_builtins/benchmarks/swebench_verified/criterion.py:72`
>   constructs its own sandbox manager — tracked in the follow-up below.

After Phase 2 (Task 0) merges: remove the callout to the swebench offender.
The anti-pattern statement remains ("criteria that allocate their own sandbox
MUST NOT"). The follow-up note moves from `docs/architecture/01_public_api.md`
to the accepted RFC.

### `docs/architecture/06_builtins.md#anti-patterns`

Current text (lines 149–151):

> - **A Criterion spawning its own sandbox.** Current known offender:
>   `ergon_builtins/benchmarks/swebench_verified/criterion.py:72`; tracked at
>   `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md`.

After Phase 2: remove the offender callout. The invariant statement at
`docs/architecture/06_builtins.md` line 104 (`Criteria MUST NOT spawn their
own sandboxes`) is strengthened to: "Enforced by
`tests/state/test_criteria_do_not_spawn_sandboxes.py` (hard-pass after
2026-04-17 RFC)."

## Alternatives considered

- **Keep `call_llm_judge()` as a first-class Protocol method.** Tentatively
  accepted. It is the only method not about sandbox/resource/event I/O — a
  convenience wrapper. If the Protocol keeps growing, extract it into an
  `LLMJudgeMixin` or helper module. Flagged as future cleanup, not a blocker.

- **Add `get_sandbox()` as the earlier draft of this RFC proposed.** Rejected:
  `ensure_sandbox()` at `criterion_runtime.py:57` already covers "provision
  or reconnect and hand back the task sandbox." A separate accessor would
  split the responsibility without benefit. Note: the bug report at
  `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md` references
  `runtime.get_sandbox()` — that proposed fix is superseded by the
  `ensure_sandbox()` + direct `sandbox_manager.get_sandbox()` path adopted here.

- **Move all Protocol methods into an abstract base class.** Rejected.
  Protocols stay structural so criterion authors do not need to inherit.
  `DefaultCriterionRuntime` does not subclass the Protocol and doesn't need to.

- **Separate Protocols for agentic vs. non-agentic criteria.** Rejected.
  Every criterion benefits uniformly from resource and DB access.

- **`db_read_session()`: read-only via session-factory split.** Deferred to v2.
  A separate read-only engine URL (pointing to a replica or using the same
  engine with `execution_options(no_autocommit=True)`) is architecturally
  cleaner but adds infra complexity. v1 uses the same `get_session()` factory
  with a documented convention ("do not write").

## Open questions

- Should `event_sink()` return a narrow interface (e.g. "emit criterion
  progress event" only) or the full `SandboxEventSink`? Narrow is safer and
  keeps criteria out of unrelated emitter surface; broad is more flexible for
  agentic criteria that want to stream their own structured updates. Decision
  deferred to implementation review.

- `db_read_session()`: read-only via session-factory split, or a regular
  session with a "please don't write" convention? Strict is safer; convention
  is cheaper. Deferred to PR 1 implementation review.

- Phase 3 audit scope: are there non-swebench criteria in `ergon_builtins/`
  that already open DB sessions directly? A one-time `grep` before PR 2
  merges will confirm whether the audit has zero or nonzero work.

## On acceptance

- [ ] Move this file from `docs/rfcs/active/` to `docs/rfcs/accepted/`.
- [ ] Update `docs/architecture/01_public_api.md#criterionruntime` to reflect
      the expanded surface (seven existing + four new methods); remove offender
      callout from anti-patterns after Phase 2.
- [ ] Update `docs/architecture/06_builtins.md` — strengthen "Criteria MUST
      NOT spawn their own sandboxes" invariant to reference hard-enforcement
      by state test; remove swebench-verified callout.
- [ ] Close `docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md`
      once Task 0 lands — move to `docs/bugs/fixed/` with `fixed_pr` set.
