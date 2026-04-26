# Core Test Logic Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove testing-specific logic that has crept into core runtime code, starting with sandbox sentinel handling, while preserving the non-null `sandbox_id` contract.

**Architecture:** Core orchestration should depend on provider-owned lifecycle APIs, not on test/stub identities or sentinel parsing. Production sandbox setup requires E2B configuration and must fail loudly if E2B is unavailable; there is no core "no remote sandbox was provisioned" fallback. Test doubles such as `StubSandboxManager`, smoke workers, smoke fixtures, local sandbox implementations, and any placeholder sentinel IDs stay under `ergon_core.test_support` and are only wired through explicitly gated harness/bootstrap paths.

**Tech Stack:** Python, FastAPI, Inngest, SQLModel, pytest, Playwright, Docker Compose.

---

## Current Findings

The immediate issue is not that placeholder sandbox IDs exist in tests. The issue is that runtime/core code knows too much about why a placeholder exists. Core should require real sandbox provisioning; test support can still provide sentinel-backed managers for unit/integration tests.

Current leaks:

- `ergon_core/ergon_core/core/providers/sandbox/manager.py` defines `StubSandboxManager` and `is_stub_sandbox_id`; the manager can continue to exist, but it belongs under `ergon_core.test_support`, not `core`.
- `ergon_core/ergon_core/core/runtime/inngest/execute_task.py` imports `StubSandboxManager` to mint skipped-task sandbox IDs.
- `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py` imports `is_stub_sandbox_id` before terminating sandboxes.
- `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py` imports `is_stub_sandbox_id` before terminating run-level sandboxes.
- `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py` currently imports `is_stub_sandbox_id` for failed-task cleanup.
- `ergon_core/ergon_core/test_support/smoke_fixtures/*` is acceptable test-owned code, but core runtime must not import it.
- `ergon_core/ergon_core/core/api/test_harness.py` is acceptable only because it is explicitly mounted behind `ENABLE_TEST_HARNESS`; this plan adds guardrails so that pattern does not spread.

## Audit Results

Audit command run on 2026-04-26:

```bash
rg "test_support|tests\.|smoke|fake|mock|stub|fixture|ENABLE_TEST|ENABLE_SMOKE|test_harness|StubSandboxManager|is_stub_sandbox_id|stub-sandbox" ergon_core/ergon_core/core
```

### Must Fix

- `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`
  - Imports `BaseSandboxManager` and `is_stub_sandbox_id`.
  - Branches on `is_stub_sandbox_id` during failed-task sandbox cleanup.
  - Classification: **test/provider sentinel knowledge leaked into runtime orchestration.**
  - Fix: route through provider-owned `terminate_sandbox_by_id`.

- `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
  - Imports `StubSandboxManager`.
  - Creates `stub_sandbox_id` for skipped tasks.
  - Comments instruct downstream teardown to inspect `is_stub_sandbox_id`.
  - Classification: **test double implementation leaked into task execution.**
  - Fix: remove the skipped-task stub path from core. If skipped tasks must emit completion events, they should still have a real sandbox ID from normal setup or the event contract should be redesigned deliberately; do not mint provider placeholders in core.

- `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py`
  - Imports and branches on `is_stub_sandbox_id`.
  - Classification: **runtime teardown knows provider sentinel details.**
  - Fix: call provider-owned lifecycle termination API.

- `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py`
  - Imports and branches on `is_stub_sandbox_id`.
  - Classification: **run cleanup knows provider sentinel details.**
  - Fix: call provider-owned lifecycle termination API.

- `ergon_core/ergon_core/core/runtime/events/task_events.py`
  - Comments describe `StubSandboxManager` and `is_stub_sandbox_id`.
  - Classification: **contract docs encode the wrong abstraction.**
  - Fix: document that production task execution uses real sandbox IDs. Test-support managers may emit sentinel IDs, but core consumers must not branch on them.

- `ergon_core/ergon_core/core/providers/sandbox/manager.py`
  - Defines `_STUB_SANDBOX_PREFIX`, `is_stub_sandbox_id`, and `StubSandboxManager`.
  - `DefaultSandboxManager.create` delegates to `StubSandboxManager` when `E2B_API_KEY` is missing.
  - Classification: **a test double is mixed into core, and core incorrectly treats missing E2B configuration as a recoverable execution mode.**
  - Fix: move `StubSandboxManager` to `ergon_core.test_support`; remove the `DefaultSandboxManager` no-E2B fallback and let `BaseSandboxManager.create` fail loudly when `E2B_API_KEY` is absent.

- `ergon_core/ergon_core/core/api/app.py`
  - Imports `ergon_core.test_support.smoke_fixtures.register_smoke_fixtures` under `settings.smoke_fixtures_enabled`.
  - Classification: **core app bootstrap imports test-support code.** The flag helps, but the dependency direction is still wrong.
  - Fix: replace this with a generic startup-plugin mechanism, then configure the smoke fixture registration callable from local/CI environment.

### Probably Fix / Rename

- `ergon_core/ergon_core/core/runtime/inngest/benchmark_run_start.py`
  - Defaults `worker_slug` to `"stub-worker"` and `evaluator_slug` to `"stub-rubric"`.
  - Classification: **not necessarily test logic, but the default names read as test doubles inside a production request contract.**
  - Fix: make both fields required. The benchmark-run request contract should not invent worker/evaluator defaults.

- `ergon_core/ergon_core/core/rl/eval_runner.py`
  - Defaults `evaluator_type` to `"stub-rubric"` and uses `"stub-worker"` when no `model_base` is provided.
  - Classification: **RL/dev utility behavior may be legitimate, but the naming implies test doubles.**
  - Fix: make evaluator/model inputs explicit. Do not default to stub worker or stub evaluator slugs.

- `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py`
  - Comment says `release-sandbox — stub`.
  - Classification: **stale implementation comment.**
  - Fix: update to lifecycle-service language when cancelled-task cleanup is wired.

### Allowed / No Code Change

- `ergon_core/ergon_core/core/api/test_harness.py`
  - Test-only router behind `ENABLE_TEST_HARNESS`.
  - Classification: **allowed explicitly gated integration surface.**
  - Constraint: may depend on test concepts, but should stay isolated to this file/package.

- `ergon_core/ergon_core/core/settings.py`
  - Defines `ENABLE_TEST_HARNESS`, `ENABLE_SMOKE_FIXTURES`, and `smoke_fixtures_enabled`.
  - Classification: **allowed configuration surface for gated dev/test behavior.**
  - Follow-up: `ENABLE_SMOKE_FIXTURES` should be replaced or backed by a generic startup-plugin setting when `core/api/app.py` is fixed.

- `ergon_core/ergon_core/core/runtime/services/task_management_service.py`
  - Comment says tests must seed `RunRecord` via factories/fixtures.
  - Classification: **allowed test guidance in invariant documentation.**
  - No runtime behavior depends on test code.

- `ergon_core/ergon_core/core/runtime/errors/delegation_errors.py`
  - Comment says missing fixtures in tests should fail loudly.
  - Classification: **allowed explanatory comment.**
  - No runtime behavior depends on test code.

- `ergon_core/ergon_core/core/providers/sandbox/manager.py`
  - ImportError fallback exception classes for missing E2B SDK.
  - Classification: **allowed optional dependency shim, but rename/comment carefully to avoid "test stub" language.**

- `ergon_core/ergon_core/core/persistence/graph/models.py`
  - Comment includes `"canonical-smoke"` as an example worker slug.
  - Classification: **allowed example but should be refreshed if smoke naming changes.**

Desired boundary:

- Core runtime may say: "terminate the sandbox for this ID."
- Core runtime may not say: "skip because this ID is a stub."
- Core production sandbox creation must fail loudly if E2B is unavailable.
- Test-support managers may use sentinel IDs, but only test-support code should create or name them.
- The `sandbox_id` field should remain non-null for normal lifecycle events that require it.

## File Structure

Create:

- `ergon_core/ergon_core/core/providers/sandbox/lifecycle.py`
  - Owns sandbox lifecycle decisions by ID.
  - Defines a termination result and termination service.
  - Does not define or parse test sentinel IDs.

- `ergon_core/ergon_core/test_support/sandbox/stub_manager.py`
  - Contains `StubSandboxManager` as a test double for unit tests and harness-specific tests.
  - Owns its sentinel prefix and any fake sandbox lifecycle bookkeeping.
  - Must not be imported by `ergon_core.core`.

- `tests/unit/sandbox/test_sandbox_lifecycle_service.py`
  - Tests real-ID termination dispatch.
  - Tests malformed or missing IDs are handled explicitly.

- `tests/unit/architecture/test_no_test_logic_in_core.py`
  - Regression guard that scans core runtime/provider modules for forbidden imports and terms.
  - Allows explicitly approved files such as `core/api/test_harness.py` and `core/settings.py`.

Modify:

- `ergon_core/ergon_core/core/providers/sandbox/manager.py`
  - Remove `is_stub_sandbox_id` from this file.
  - Move `StubSandboxManager` to `ergon_core/ergon_core/test_support/sandbox/stub_manager.py`.
  - Remove `DefaultSandboxManager.create`'s no-E2B fallback so production setup inherits the loud failure in `BaseSandboxManager.create`.

- `ergon_core/ergon_core/core/providers/sandbox/__init__.py`
  - Export lifecycle primitives that runtime code is allowed to use.

- `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
  - Stop importing `StubSandboxManager`.
  - Remove skipped-task placeholder minting from core.

- `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py`
  - Replace `is_stub_sandbox_id` branching with the lifecycle service termination call.

- `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py`
  - Replace `is_stub_sandbox_id` branching with the lifecycle service termination call.

- `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`
  - Replace failed-task cleanup branching with the lifecycle service termination call.

- `ergon_core/ergon_core/core/runtime/events/task_events.py`
  - Update comments that reference stub mode or `is_stub_sandbox_id`.

- `ergon_core/ergon_core/core/api/app.py`
  - Remove direct imports from `ergon_core.test_support`.
  - Load optional startup hooks through a generic plugin setting.

- `ergon_core/ergon_core/core/settings.py`
  - Add a generic startup plugin setting.
  - Keep test harness routing gated, but stop hardcoding smoke fixture registration in core app startup.

- `tests/unit/runtime/test_failed_task_sandbox_cleanup.py`
  - Update mocks to target the lifecycle service instead of `BaseSandboxManager` directly.

## Task 1: Add Provider-Owned Sandbox Lifecycle API

**Files:**

- Create: `ergon_core/ergon_core/core/providers/sandbox/lifecycle.py`
- Test: `tests/unit/sandbox/test_sandbox_lifecycle_service.py`

- [ ] **Step 1: Write failing lifecycle service tests**

Create `tests/unit/sandbox/test_sandbox_lifecycle_service.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.sandbox.lifecycle import (
    SandboxTerminationReason,
    terminate_sandbox_by_id,
)


@pytest.mark.asyncio
async def test_terminate_sandbox_by_id_dispatches_real_ids() -> None:
    with patch(
        "ergon_core.core.providers.sandbox.manager.BaseSandboxManager.terminate_by_sandbox_id",
        new=AsyncMock(return_value=True),
    ) as terminate:
        result = await terminate_sandbox_by_id("sbx-live-123")

    terminate.assert_awaited_once_with("sbx-live-123")
    assert result.terminated is True
    assert result.reason == SandboxTerminationReason.TERMINATED


@pytest.mark.asyncio
async def test_terminate_sandbox_by_id_handles_missing_id_explicitly() -> None:
    result = await terminate_sandbox_by_id(None)

    assert result.terminated is False
    assert result.reason == SandboxTerminationReason.MISSING_ID
    assert result.sandbox_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/sandbox/test_sandbox_lifecycle_service.py -q
```

Expected: FAIL because `ergon_core.core.providers.sandbox.lifecycle` does not exist yet.

- [ ] **Step 3: Add lifecycle service**

Create `ergon_core/ergon_core/core/providers/sandbox/lifecycle.py`:

```python
"""Provider-owned sandbox lifecycle helpers.

Runtime orchestration code should not inspect sandbox ID sentinels. It should
delegate lifecycle operations here and let the provider layer terminate real
sandboxes. Test-support sentinel IDs are owned by test-support managers, not by
core runtime.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxTerminationReason(StrEnum):
    TERMINATED = "terminated"
    NOT_FOUND_OR_ALREADY_CLOSED = "not_found_or_already_closed"
    MISSING_ID = "missing_id"
    ERROR = "error"


class SandboxTerminationResult(BaseModel):
    sandbox_id: str | None
    terminated: bool
    reason: SandboxTerminationReason


async def terminate_sandbox_by_id(sandbox_id: str | None) -> SandboxTerminationResult:
    """Terminate a sandbox ID behind one runtime-facing lifecycle boundary."""
    if sandbox_id is None:
        return SandboxTerminationResult(
            sandbox_id=None,
            terminated=False,
            reason=SandboxTerminationReason.MISSING_ID,
        )

    try:
        from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

        terminated = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.error("Failed to terminate sandbox %s", sandbox_id, exc_info=True)
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=False,
            reason=SandboxTerminationReason.ERROR,
        )

    return SandboxTerminationResult(
        sandbox_id=sandbox_id,
        terminated=terminated,
        reason=(
            SandboxTerminationReason.TERMINATED
            if terminated
            else SandboxTerminationReason.NOT_FOUND_OR_ALREADY_CLOSED
        ),
    )
```

- [ ] **Step 4: Run lifecycle tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/sandbox/test_sandbox_lifecycle_service.py -q
```

Expected: PASS.

## Task 2: Move Stub Sandbox Manager Out of Core

**Files:**

- Modify: `ergon_core/ergon_core/core/providers/sandbox/manager.py`
- Modify: `ergon_core/ergon_core/core/providers/sandbox/__init__.py`
- Create: `ergon_core/ergon_core/test_support/sandbox/__init__.py`
- Create: `ergon_core/ergon_core/test_support/sandbox/stub_manager.py`
- Test: `tests/unit/sandbox/test_sandbox_lifecycle_service.py`
- Test: `tests/unit/smoke_base/test_smoke_sandbox_manager.py`

- [ ] **Step 1: Update exports**

Modify `ergon_core/ergon_core/core/providers/sandbox/__init__.py` to export the lifecycle API:

```python
from ergon_core.core.providers.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
    terminate_sandbox_by_id,
)
```

Add these names to `__all__`:

```python
    "SandboxTerminationReason",
    "SandboxTerminationResult",
    "terminate_sandbox_by_id",
```

- [ ] **Step 2: Move `StubSandboxManager` to test support**

Create `ergon_core/ergon_core/test_support/sandbox/__init__.py`:

```python
"""Test-support sandbox doubles."""

from ergon_core.test_support.sandbox.stub_manager import StubSandboxManager

__all__ = ["StubSandboxManager"]
```

Create `ergon_core/ergon_core/test_support/sandbox/stub_manager.py`:

```python
"""Sandbox manager test double.

This class exists for unit tests and test harnesses that need a concrete
manager object without provisioning E2B. Production/core code must not import
this module.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import AsyncSandbox, BaseSandboxManager

logger = logging.getLogger(__name__)


class _StubSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id

    async def kill(self) -> None:
        return None


class StubSandboxManager(BaseSandboxManager):
    """No-op sandbox manager for tests.

    ``create`` returns a test-owned sentinel ID. Production/core code must not
    create or inspect this ID format.
    """

    _PREFIX = "stub-sandbox-"

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        sandbox_id = f"{self._PREFIX}{sandbox_key}"
        logger.info(
            "Returning test stub sandbox id %s for task %s",
            sandbox_id,
            sandbox_key,
        )
        self._ensure_registries(sandbox_key)
        self._sandboxes[sandbox_key] = _StubSandbox(sandbox_id)  # type: ignore[assignment]
        self._run_ids[sandbox_key] = run_id
        self._display_task_ids[sandbox_key] = display_task_id or sandbox_key
        self._sandbox_manager_classes[sandbox_key] = type(self)
        return sandbox_id

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        return None

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        self._file_registries.pop(task_id, None)
        self._created_files_registry.pop(task_id, None)
        self._run_ids.pop(task_id, None)
        self._display_task_ids.pop(task_id, None)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        return True
```

Then remove these symbols from `ergon_core/ergon_core/core/providers/sandbox/manager.py`:

```python
_STUB_SANDBOX_PREFIX = "stub-sandbox-"


def is_stub_sandbox_id(sandbox_id: JsonValue) -> bool:
    ...


class StubSandboxManager(BaseSandboxManager):
    ...
```

- [ ] **Step 3: Remove core no-E2B fallback**

Do not add any `DefaultSandboxManager.create` fallback. In `ergon_core/ergon_core/core/providers/sandbox/manager.py`, either delete the `DefaultSandboxManager.create` override entirely or reduce `DefaultSandboxManager` to dependency hooks only:

```python
class DefaultSandboxManager(BaseSandboxManager):
    """No custom dependencies. Used by benchmarks without specific sandbox setup."""

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        pass
```

This intentionally preserves `BaseSandboxManager.create`'s existing loud failure when `E2B_API_KEY` is missing.

- [ ] **Step 4: Run sandbox tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/sandbox/test_sandbox_lifecycle_service.py tests/unit/smoke_base/test_smoke_sandbox_manager.py -q
```

Expected: PASS.

## Task 3: Remove Skipped-Task Placeholder Minting from Task Execution

**Files:**

- Modify: `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
- Test: `tests/unit/runtime/test_child_function_payloads.py`
- Test: `tests/unit/runtime/test_worker_execute_output_failure.py`

- [ ] **Step 1: Remove skipped-task stub manager import**

In `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`, replace:

```python
from ergon_core.core.providers.sandbox.manager import StubSandboxManager
```

with no sandbox-manager import. `execute_task.py` should not import `StubSandboxManager`, `make_noop_sandbox_id`, or any test-support sandbox module.

Then replace the skipped-task block:

```python
if prepared.skipped:
    logger.info(
        "task-execute skipped task_id=%s reason=%s",
        payload.task_id,
        prepared.skip_reason,
    )
    stub_sandbox_id = await StubSandboxManager().create(
        prepared.node_id,
        run_id=payload.run_id,
        display_task_id=prepared.node_id,
    )
    await _emit_task_completed(payload, prepared, stub_sandbox_id)
    return TaskExecuteResult(
        run_id=payload.run_id,
        task_id=payload.task_id,
        execution_id=prepared.execution_id,
        success=True,
        skipped=True,
        skip_reason=prepared.skip_reason,
    )
```

with:

```python
if prepared.skipped:
    raise ContractViolationError(
        "Skipped task execution cannot emit task/completed without a real sandbox_id. "
        "Introduce a first-class task/skipped event before supporting skipped tasks."
    )
```

Rationale: production has no "no remote sandbox was provisioned" path. If skipped tasks become a real product feature, they need their own explicit event/propagation contract instead of fake sandbox IDs.

- [ ] **Step 2: Add a regression test for skipped-task contract failure**

Add a focused unit test for `execute_task_fn`'s skipped branch if there is an existing task-execution test harness. If no focused harness exists, add this behavior to the architecture guard:

```python
def test_core_task_execution_does_not_mint_placeholder_sandbox_ids() -> None:
    path = CORE / "runtime" / "inngest" / "execute_task.py"
    text = path.read_text()

    assert "StubSandboxManager" not in text
    assert "make_noop_sandbox_id" not in text
    assert "stub_sandbox_id" not in text
```

- [ ] **Step 3: Compile task execution module**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run python -m py_compile ergon_core/ergon_core/core/runtime/inngest/execute_task.py
```

Expected: no output.

- [ ] **Step 4: Run targeted runtime tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/runtime/test_child_function_payloads.py tests/unit/runtime/test_worker_execute_output_failure.py -q
```

Expected: PASS.

## Task 4: Route All Runtime Teardown Through Lifecycle Service

**Files:**

- Modify: `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`
- Modify: `tests/unit/runtime/test_failed_task_sandbox_cleanup.py`

- [ ] **Step 1: Update failed-task cleanup test**

Change `tests/unit/runtime/test_failed_task_sandbox_cleanup.py` to patch the provider lifecycle API:

```python
from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)
from ergon_core.core.runtime.inngest.propagate_execution import _terminate_failed_task_sandbox


@pytest.mark.asyncio
async def test_failed_task_sandbox_cleanup_delegates_to_lifecycle_service() -> None:
    result = SandboxTerminationResult(
        sandbox_id="sbx-real",
        terminated=True,
        reason=SandboxTerminationReason.TERMINATED,
    )
    with patch(
        "ergon_core.core.runtime.inngest.propagate_execution.terminate_sandbox_by_id",
        new=AsyncMock(return_value=result),
    ) as terminate:
        await _terminate_failed_task_sandbox("sbx-real")

    terminate.assert_awaited_once_with("sbx-real")
```

- [ ] **Step 2: Update failed-task cleanup implementation**

In `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`, replace:

```python
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager, is_stub_sandbox_id
```

with:

```python
from ergon_core.core.providers.sandbox.lifecycle import terminate_sandbox_by_id
```

Replace `_terminate_failed_task_sandbox` with:

```python
async def _terminate_failed_task_sandbox(sandbox_id: str | None) -> None:
    result = await terminate_sandbox_by_id(sandbox_id)
    if not result.terminated:
        logger.info(
            "failed-task sandbox cleanup did not terminate sandbox_id=%s reason=%s",
            result.sandbox_id,
            result.reason,
        )
```

- [ ] **Step 3: Update evaluator cleanup**

In `ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py`, replace imports of `BaseSandboxManager` and `is_stub_sandbox_id` with:

```python
from ergon_core.core.providers.sandbox.lifecycle import terminate_sandbox_by_id
```

Replace `_terminate_sandbox` with:

```python
async def _terminate_sandbox(sandbox_id: str) -> None:
    """Terminate the task's sandbox through the provider lifecycle boundary."""
    result = await terminate_sandbox_by_id(sandbox_id)
    logger.info(
        "Evaluator sandbox cleanup sandbox_id=%s terminated=%s reason=%s",
        result.sandbox_id,
        result.terminated,
        result.reason,
    )
```

- [ ] **Step 4: Update run cleanup**

In `ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py`, replace:

```python
from ergon_core.core.providers.sandbox.manager import (
    BaseSandboxManager,
    is_stub_sandbox_id,
)
```

with:

```python
from ergon_core.core.providers.sandbox.lifecycle import terminate_sandbox_by_id
```

Replace the branch over `sandbox_id` with:

```python
sandbox_result = await terminate_sandbox_by_id(
    sandbox_id if isinstance(sandbox_id, str) else None
)
sandbox_terminated = sandbox_result.terminated

if sandbox_id is not None and not isinstance(sandbox_id, str):
    logger.warning(
        "run-cleanup run_id=%s: sandbox_id has unexpected type %s, skipping termination",
        run_id,
        type(sandbox_id).__name__,
    )
```

- [ ] **Step 5: Run targeted teardown tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/runtime/test_failed_task_sandbox_cleanup.py tests/unit/sandbox/test_sandbox_lifecycle_service.py -q
```

Expected: PASS.

## Task 5: Remove Test-Support Imports from App Bootstrap

**Files:**

- Modify: `ergon_core/ergon_core/core/api/app.py`
- Modify: `ergon_core/ergon_core/core/settings.py`
- Test: `tests/unit/test_test_harness.py`
- Test: `tests/unit/architecture/test_no_test_logic_in_core.py`

- [ ] **Step 1: Add a generic startup-plugin setting**

In `ergon_core/ergon_core/core/settings.py`, add a string setting that can hold comma-separated import specs:

```python
startup_plugin_specs: str = Field(
    default="",
    validation_alias=AliasChoices("ERGON_STARTUP_PLUGINS"),
)
```

Add a helper property:

```python
@property
def startup_plugins(self) -> tuple[str, ...]:
    return tuple(
        spec.strip()
        for spec in self.startup_plugin_specs.split(",")
        if spec.strip()
    )
```

Keep `enable_test_harness` for mounting the harness router. Treat `enable_smoke_fixtures` as compatibility only until callers are moved to `ERGON_STARTUP_PLUGINS`.

- [ ] **Step 2: Add an app-local plugin loader**

In `ergon_core/ergon_core/core/api/app.py`, add:

```python
from importlib import import_module


def _run_startup_plugins(plugin_specs: tuple[str, ...]) -> None:
    for spec in plugin_specs:
        module_name, sep, attr_name = spec.partition(":")
        if not sep or not module_name or not attr_name:
            raise RuntimeError(
                "Invalid ERGON_STARTUP_PLUGINS entry "
                f"{spec!r}; expected 'module:function'"
            )
        module = import_module(module_name)
        plugin = getattr(module, attr_name)
        plugin()
```

Then replace:

```python
if settings.smoke_fixtures_enabled:
    from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures

    register_smoke_fixtures()
```

with:

```python
_run_startup_plugins(settings.startup_plugins)
```

- [ ] **Step 3: Preserve local/CI smoke fixture registration through configuration**

Update local and CI smoke environment setup to use:

```bash
ERGON_STARTUP_PLUGINS=ergon_core.test_support.smoke_fixtures:register_smoke_fixtures
```

Candidate files to inspect and update:

- `docker-compose.yml`
- `.github/workflows/e2e-benchmarks.yml`
- `scripts/smoke_local_up.sh`
- `scripts/smoke_local_run.sh`

Do not keep a direct import of `ergon_core.test_support` in `core/api/app.py`.

- [ ] **Step 4: Add tests for startup plugin loading**

In `tests/unit/test_test_harness.py`, add a focused test for `_run_startup_plugins` using a standard-library callable that is safe to call, or a tiny in-test module fixture if one already exists. If a direct callable test is awkward, test invalid config instead:

```python
import pytest

from ergon_core.core.api.app import _run_startup_plugins


def test_startup_plugin_loader_rejects_invalid_specs() -> None:
    with pytest.raises(RuntimeError, match="expected 'module:function'"):
        _run_startup_plugins(("ergon_core.test_support.smoke_fixtures",))
```

- [ ] **Step 5: Run app/test-harness tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/test_test_harness.py -q
```

Expected: PASS.

## Task 6: Add Architecture Guard for Test Logic in Core

**Files:**

- Create: `tests/unit/architecture/test_no_test_logic_in_core.py`

- [ ] **Step 1: Write architecture guard**

Create `tests/unit/architecture/test_no_test_logic_in_core.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "ergon_core" / "ergon_core" / "core"

ALLOWED_FILES = {
    CORE / "api" / "test_harness.py",
    CORE / "settings.py",
}

FORBIDDEN_IMPORT_SNIPPETS = (
    "ergon_core.test_support",
    "tests.",
)

FORBIDDEN_CORE_TEST_DOUBLE_TERMS = (
    "StubSandboxManager",
    "is_stub_sandbox_id",
    "stub-sandbox-",
)


def _core_python_files() -> list[Path]:
    return [
        path
        for path in CORE.rglob("*.py")
        if path not in ALLOWED_FILES and "__pycache__" not in path.parts
    ]


def test_core_does_not_import_test_support_or_tests() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        text = path.read_text()
        for snippet in FORBIDDEN_IMPORT_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []


def test_core_does_not_define_or_branch_on_stub_sandbox_terms() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        text = path.read_text()
        for term in FORBIDDEN_CORE_TEST_DOUBLE_TERMS:
            if term in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {term!r}")

    assert offenders == []
```

- [ ] **Step 2: Run architecture guard**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/architecture/test_no_test_logic_in_core.py -q
```

Expected: PASS after Tasks 1-4. If it fails, move the offending logic behind provider/test-support boundaries instead of weakening the guard.

## Task 7: Clean Comments and Event Contract Language

**Files:**

- Modify: `ergon_core/ergon_core/core/runtime/events/task_events.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
- Modify: `ergon_core/ergon_core/core/providers/sandbox/manager.py`

- [ ] **Step 1: Remove "stub" and no-sandbox fallback terminology from core comments**

Replace comments that describe no-E2B behavior as "stub mode" or "provider no-op sandbox ID" with loud production setup language.

In `task_events.py`, replace the existing stub comment with:

```python
# Production task execution emits real sandbox IDs. Test-support managers may
# use sentinel IDs, but core event consumers must not parse or branch on those
# sentinel formats.
```

- [ ] **Step 2: Search for remaining core stub terms**

Run:

```bash
rg "StubSandboxManager|is_stub_sandbox_id|stub-sandbox|stub mode|stub sandbox" ergon_core/ergon_core/core
```

Expected: no matches. If matches remain in core runtime/provider code, rewrite them or move the implementation to `test_support`.

## Task 8: Run Focused Verification

**Files:**

- No source edits.

- [ ] **Step 1: Compile touched Python files**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run python -m py_compile \
  ergon_core/ergon_core/core/providers/sandbox/lifecycle.py \
  ergon_core/ergon_core/core/providers/sandbox/manager.py \
  ergon_core/ergon_core/core/runtime/inngest/execute_task.py \
  ergon_core/ergon_core/core/runtime/inngest/check_evaluators.py \
  ergon_core/ergon_core/core/runtime/inngest/run_cleanup.py \
  ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py
```

Expected: no output.

- [ ] **Step 2: Run unit tests**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest \
  tests/unit/sandbox/test_sandbox_lifecycle_service.py \
  tests/unit/runtime/test_failed_task_sandbox_cleanup.py \
  tests/unit/runtime/test_worker_execute_output_failure.py \
  tests/unit/smoke_base/test_smoke_sandbox_manager.py \
  tests/unit/architecture/test_no_test_logic_in_core.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run local canonical smoke e2es**

Run:

```bash
ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@localhost:5433/ergon \
INNGEST_API_BASE_URL=http://localhost:8289 \
INNGEST_DEV=1 \
INNGEST_EVENT_KEY=dev \
ERGON_API_BASE_URL=http://127.0.0.1:9000 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 \
ENABLE_TEST_HARNESS=1 \
TEST_HARNESS_SECRET=local-dev \
SCREENSHOT_DIR=/tmp/playwright \
SMOKE_COHORT_SIZE=1 \
PYTHONPATH="ergon_core:ergon_builtins" \
uv run pytest tests/e2e/test_researchrubrics_smoke.py tests/e2e/test_minif2f_smoke.py tests/e2e/test_swebench_smoke.py -q -s --timeout=300 --tb=short
```

Expected: all three benchmark smoke tests pass. The sad-path shape should remain:

- `l_2` fails.
- `l_3` is blocked and never starts.
- Independent leaves complete.
- Run status is `FAILED`.
- Sandbox lifecycle events are symmetric for created/closed sandbox IDs.

## Task 9: Close Remaining Audit Findings

**Files:**

- Modify: `ergon_core/ergon_core/core/runtime/inngest/benchmark_run_start.py`
- Modify: `ergon_core/ergon_core/core/rl/eval_runner.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py`
- Update: `tests/unit/architecture/test_no_test_logic_in_core.py`

- [ ] **Step 1: Re-run the audit search and compare against the inventory**

Run:

```bash
rg "test_support|tests\\.|smoke|fake|mock|stub|fixture|ENABLE_TEST|ENABLE_SMOKE" ergon_core/ergon_core/core
```

Expected remaining matches should be limited to the `Allowed / No Code Change` section above. Any match from `Must Fix` should be gone.

- [ ] **Step 2: Fix request-contract defaults that read as test doubles**

In `ergon_core/ergon_core/core/runtime/inngest/benchmark_run_start.py`, make worker/evaluator slugs explicit instead of defaulting to test-looking values:

```python
class BenchmarkRunRequest(InngestEventContract):
    """CLI sends this to request a full benchmark run."""

    name: ClassVar[str] = "benchmark/run-request"

    benchmark_slug: str
    model: str
    worker_slug: str
    evaluator_slug: str
    cohort_name: str = ""  # slopcop: ignore[no-str-empty-default]
```

Then update call sites/tests that construct `BenchmarkRunRequest` without `worker_slug` or `evaluator_slug` so they pass concrete slugs.

- [ ] **Step 3: Require explicit RL eval runner inputs**

In `ergon_core/ergon_core/core/rl/eval_runner.py`, replace `"stub-rubric"` defaults with required evaluator arguments:

```python
async def watch_and_evaluate(
    checkpoint_dir: str,
    benchmark_type: str,
    *,
    evaluator_type: str,
    model_base: str,
    poll_interval_s: int = 60,
    eval_limit: int | None = None,
    on_checkpoint_cmd: str | None = None,
    external_cmd_timeout_s: int = 600,
) -> None:
```

For `_run_local_eval`, make `model_base` required:

```python
async def _run_local_eval(
    ckpt: CheckpointInfo,
    *,
    benchmark_type: str,
    evaluator_type: str,
    model_base: str,
    eval_limit: int | None,
) -> int:
```

Then replace:

```python
model_target = f"vllm:{ckpt.path}" if model_base else "stub-worker"
```

with:

```python
model_target = f"vllm:{ckpt.path}"
```

Apply the same required `evaluator_type` and `model_base` signatures to `evaluate_checkpoint`. Callers must pass concrete values.

- [ ] **Step 4: Update cancelled-task cleanup comment**

In `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py`, replace:

```python
2. release-sandbox — stub (pending sandbox management module)
```

with:

```python
2. release-sandbox — routed through the sandbox lifecycle provider when an
   execution has an associated sandbox.
```

- [ ] **Step 5: Keep the allowed list narrow**

Do not add broad exemptions to `tests/unit/architecture/test_no_test_logic_in_core.py`. The allowed files should remain:

```python
ALLOWED_FILES = {
    CORE / "api" / "test_harness.py",
    CORE / "settings.py",
}
```

If the architecture guard catches a new file, fix the dependency direction instead of adding the file to `ALLOWED_FILES`.

- [ ] **Step 6: Fix any new offenders with the same pattern**

For each offender:

1. Move test-owned implementation into `ergon_core/ergon_core/test_support`.
2. Leave only a production abstraction in `ergon_core/ergon_core/core`.
3. Wire the test implementation from an explicitly gated bootstrap path.
4. Add the offender term to `tests/unit/architecture/test_no_test_logic_in_core.py` if it should never recur.

- [ ] **Step 7: Re-run architecture guard**

Run:

```bash
PYTHONPATH="ergon_core:ergon_builtins" uv run pytest tests/unit/architecture/test_no_test_logic_in_core.py -q
```

Expected: PASS.

## Self-Review

- Spec coverage: covers the selected sandbox stub leak and widens scope to an architectural audit for test logic in core.
- Placeholder scan: no unresolved implementation placeholders are used as plan content; the audit task gives concrete classification and remediation rules.
- Type consistency: lifecycle names are consistent across tasks: `terminate_sandbox_by_id`, `SandboxTerminationResult`, and `SandboxTerminationReason`.
- Scope check: intentionally scoped to test-logic leakage in core, with sandbox lifecycle as the first concrete refactor and a guardrail test to prevent recurrence.

