---
status: active
opened: 2026-04-18
author: agent
architecture_refs: [docs/architecture/05_dashboard.md#invariants]
supersedes: []
superseded_by: null
---

# RFC: Contract test enforcing dashboard event wiring

## Problem

The Layer 5 invariant "every persistent backend state change has a corresponding
`dashboard/*` event" (`docs/architecture/05_dashboard.md#invariants`) has no
enforcement today. It is review-only, and review has failed: 9 of 12
`DashboardEmitter` methods are defined but never invoked from runtime code (bug
`docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md`). The gap
was invisible until a grep.

### Current wiring state

`DashboardEmitter` is defined at
`ergon_core/ergon_core/core/dashboard/emitter.py:51`. It exposes 12 public
methods:

| Method | Status | Call site |
|---|---|---|
| `graph_mutation` | **WIRED** | `task_management_service.py:113` — `self._graph_repo.add_mutation_listener(dashboard_emitter.graph_mutation)` |
| `on_context_event` | **WIRED** | `worker_execute.py:81` — `context_event_repo.add_listener(dashboard_emitter.on_context_event)` |
| `cohort_updated` | **WIRED (indirect)** | `emitter.py:467` via `emit_cohort_updated_for_run`, called from `complete_workflow.py:48` |
| `register_execution` | WIRED (not a dashboard event; called at `worker_execute.py:82`) | — |
| `workflow_started` | **UNWIRED** | zero call sites in `ergon_core/`, `ergon_builtins/`, `ergon_infra/` |
| `workflow_completed` | **UNWIRED** | zero call sites |
| `task_status_changed` | **UNWIRED** | zero call sites |
| `task_evaluation_updated` | **UNWIRED** | zero call sites |
| `task_cancelled` | **UNWIRED** | zero call sites |
| `resource_published` | **UNWIRED** | zero call sites |
| `thread_message_created` | **UNWIRED** | zero call sites |
| `sandbox_created` | **UNWIRED** — `DashboardEmitterSandboxEventSink` calls it (`event_sink.py:88`) but the sink has no constructor site (tracked in `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md`) |
| `sandbox_command` | **UNWIRED** — same reason (`event_sink.py:107`) |
| `sandbox_closed` | **UNWIRED** — same reason (`event_sink.py:124`) |

**Confirmed by grep:**

```
rg -n '\.(task_status_changed|workflow_started|workflow_completed|resource_published| \
  thread_message_created|task_evaluation_updated|task_cancelled)\(' \
  ergon_core ergon_builtins ergon_infra
```

Zero matches outside `emitter.py` and `event_contracts.py`.

A parallel gap exists on the frontend: every `mutation_type` variant in
`MutationTypeSchema` (`ergon-dashboard/src/features/graph/contracts/graphMutations.ts:6`)
must have a matching `case` arm in `applyGraphMutation`
(`ergon-dashboard/src/features/graph/state/graphMutationReducer.ts:122`). The
reducer is currently exhaustive and has a `never`-typed default (`graphMutationReducer.ts:188`),
but there is no automated assertion that it stays that way when a new
`mutation_type` is added on the Python side.

## Proposal

Three pieces, in order of implementation cost:

1. **Backend contract test** (`tests/contract/test_dashboard_emitter_wiring.py`).
   Use `inspect` on `DashboardEmitter` to enumerate public async methods. For
   each method name, scan `ergon_core/`, `ergon_builtins/`, and `ergon_infra/`
   for a call pattern matching `\.{name}\(` or
   `add_listener\(.*\.{name}\b`. Zero call sites fails with a message pointing
   at the method and this RFC.

   Skip list: `register_execution` (not a dashboard event — internal mapping
   helper). The sandbox trio (`sandbox_created`, `sandbox_command`,
   `sandbox_closed`) count `DashboardEmitterSandboxEventSink` as their
   proof-of-wiring because the sink forwards to them; the separate
   sink-activation bug is tracked independently.

2. **Frontend mutation-kind coverage test**
   (`ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts`).
   Import the `MutationTypeSchema` enum values and `applyGraphMutation`. Assert
   that passing a synthetic mutation of each kind into `applyGraphMutation` does
   not fall through to the `default` branch (i.e., the mutation does not appear
   in `state.unhandledMutations`). Missing branch fails the build.

3. **Architecture doc table** — inline in `docs/architecture/05_dashboard.md`,
   listing each emitter method and its call site(s), updated whenever the
   contract test enumeration changes.

Wire test (1) into `pnpm run test:be:state` (the `tests/state/` suite runs under
`pnpm run test:be:fast`); test (2) into `pnpm -C ergon-dashboard run test:contracts`.

## Architecture overview

### Before (today)

```
DashboardEmitter methods (12)
  ├── graph_mutation           ← wired via listener
  ├── on_context_event         ← wired via listener
  ├── cohort_updated           ← wired (indirect) via emit_cohort_updated_for_run
  ├── register_execution       ← wired (internal helper, not a dashboard event)
  └── 8 remaining methods      ← DEAD — defined, never called
                                  CI does not catch this
```

### After (this RFC, post bug fix)

```
DashboardEmitter methods (12)
  ├── graph_mutation           ← wired: task_management_service.py:113
  ├── on_context_event         ← wired: worker_execute.py:81
  ├── cohort_updated           ← wired: complete_workflow.py:48
  ├── register_execution       ← wired (exempt from contract test)
  ├── workflow_started         ← wired: start_workflow.py (after bug fix)
  ├── workflow_completed       ← wired: complete_workflow.py (after bug fix)
  ├── task_status_changed      ← wired: task_management_service.py (after bug fix)
  ├── task_evaluation_updated  ← wired: evaluate_task_run.py (after bug fix)
  ├── task_cancelled           ← wired: cleanup_cancelled_task.py (after bug fix)
  ├── resource_published       ← wired: sandbox_resource_publisher (after bug fix)
  ├── thread_message_created   ← wired: messaging service (after bug fix)
  ├── sandbox_created          ← wired via DashboardEmitterSandboxEventSink
  ├── sandbox_command          ← wired via DashboardEmitterSandboxEventSink
  └── sandbox_closed           ← wired via DashboardEmitterSandboxEventSink

contract test runs in CI
  → zero-call-site emitter method → test FAILS with actionable message
  → new mutation_type without reducer → TS test FAILS
```

### Contract test data flow

```
test_dashboard_emitter_wiring.py
  1. inspect.getmembers(DashboardEmitter) → list of public async method names
  2. For each name not in EXEMPT_METHODS:
       scan ergon_core/, ergon_builtins/, ergon_infra/ for
         \.{name}\(  OR  add_listener\(.*\.{name}\b
  3. If no hits → pytest.fail() with method name + file path + RFC reference
```

## Type / interface definitions

No new types are introduced. The contract test operates entirely through
`inspect` and `ast`-free text scanning. For clarity, the skip list is defined
as a module-level constant:

```python
# ergon/tests/contract/test_dashboard_emitter_wiring.py (top of file)

# Methods exempt from the call-site requirement.
# register_execution: internal mapping helper, not a dashboard event.
# Sandbox trio: DashboardEmitterSandboxEventSink (event_sink.py) serves as
#   their wiring proof; the sink-activation gap is tracked separately.
_EXEMPT_METHODS: frozenset[str] = frozenset(
    {
        "register_execution",
        "sandbox_created",
        "sandbox_command",
        "sandbox_closed",
    }
)
```

## Full implementations

### Backend contract test

```python
# ergon/tests/contract/test_dashboard_emitter_wiring.py
"""Contract test: every DashboardEmitter public method must have at least one
call site in ergon_core/, ergon_builtins/, or ergon_infra/.

Fails CI when an emitter method is added without a corresponding call site.
See docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path
from typing import Final

import pytest

from ergon_core.core.dashboard.emitter import DashboardEmitter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Paths to scan (relative to the repo root, which is determined at runtime).
_SCAN_PACKAGES: Final[tuple[str, ...]] = (
    "ergon_core",
    "ergon_builtins",
    "ergon_infra",
)

# Files that DEFINE the emitter — excluded from the scan so self-references
# inside emitter.py don't count as call sites.
_DEFINITION_FILES: Final[frozenset[str]] = frozenset(
    {
        "ergon_core/ergon_core/core/dashboard/emitter.py",
        "ergon_core/ergon_core/core/dashboard/event_contracts.py",
        "ergon_core/ergon_core/core/providers/sandbox/event_sink.py",
    }
)

# Methods exempt from the zero-call-sites check.
# register_execution: internal mapping helper, not a dashboard event.
# Sandbox trio: DashboardEmitterSandboxEventSink (event_sink.py) is their
#   proof-of-wiring; the sink-activation gap is a separate bug.
_EXEMPT_METHODS: Final[frozenset[str]] = frozenset(
    {
        "register_execution",
        "sandbox_created",
        "sandbox_command",
        "sandbox_closed",
    }
)


def _repo_root() -> Path:
    """Find the repo root by walking up from this file until pyproject.toml
    is found, or fall back to the tests/ grandparent."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return p.parent.parent.parent


def _emitter_method_names() -> list[str]:
    """Return public async method names on DashboardEmitter."""
    return [
        name
        for name, member in inspect.getmembers(DashboardEmitter, predicate=inspect.isfunction)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    ]


def _call_patterns(method_name: str) -> list[str]:
    """Return the grep patterns that count as proof-of-wiring for a method.

    Accepts:
      - Direct call:      .method_name(
      - Listener wiring:  add_listener(...emitter.method_name  (no open paren needed)
      - Listener wiring:  add_mutation_listener(...emitter.method_name
    """
    return [
        rf"\.{re.escape(method_name)}\(",
        rf"add_listener\(.*\.{re.escape(method_name)}\b",
        rf"add_mutation_listener\(.*\.{re.escape(method_name)}\b",
    ]


def _has_call_site(method_name: str, repo_root: Path) -> bool:
    """Return True if at least one non-definition file contains a call site."""
    for package in _SCAN_PACKAGES:
        package_path = repo_root / package
        if not package_path.exists():
            continue
        for py_file in package_path.rglob("*.py"):
            rel = str(py_file.relative_to(repo_root))
            if rel in _DEFINITION_FILES:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in _call_patterns(method_name):
                if re.search(pattern, source):
                    return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDashboardEmitterWiring:
    """Every public DashboardEmitter method must have at least one call site."""

    def test_no_unwired_methods(self) -> None:
        """Enumerate all public async methods; fail if any have zero call sites.

        The full list of unwired methods is reported in a single failure so the
        developer sees all gaps at once rather than fixing one at a time.
        """
        repo_root = _repo_root()
        methods = _emitter_method_names()

        unwired: list[str] = []
        for method_name in methods:
            if method_name in _EXEMPT_METHODS:
                continue
            if not _has_call_site(method_name, repo_root):
                unwired.append(method_name)

        if unwired:
            pytest.fail(
                "DashboardEmitter methods with zero call sites in "
                "ergon_core/, ergon_builtins/, ergon_infra/:\n"
                + "\n".join(f"  - {m}" for m in sorted(unwired))
                + "\n\nFor each method, add a call site at the point of the "
                "corresponding state mutation.  See:\n"
                "  docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md\n"
                "  docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md",
            )

    @pytest.mark.parametrize("method_name", _emitter_method_names())
    def test_method_is_async(self, method_name: str) -> None:
        """Guard against accidentally making an emitter method sync.

        All DashboardEmitter public methods must be async — they call
        inngest_client.send(), which is a coroutine.
        """
        member = getattr(DashboardEmitter, method_name)
        assert inspect.iscoroutinefunction(member), (
            f"DashboardEmitter.{method_name} is not async. "
            "All emitter methods must be async coroutines."
        )

    def test_exempt_methods_still_exist(self) -> None:
        """The exempt list must not drift from the actual class definition.

        If an exempt method is renamed or removed, this test catches it so the
        skip list is kept honest.
        """
        all_methods = set(_emitter_method_names())
        # Exempt methods that are NOT async (register_execution) are excluded
        # from the async method list; check all members including sync ones.
        all_public = {
            name
            for name, _ in inspect.getmembers(DashboardEmitter, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        missing_from_class = _EXEMPT_METHODS - all_public
        assert not missing_from_class, (
            f"Exempt methods not found on DashboardEmitter: {missing_from_class}. "
            "Update _EXEMPT_METHODS in this file."
        )
```

### Frontend mutation-kind coverage test

```typescript
// ergon/ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts
/**
 * Contract test: every MutationType variant must have a matching case arm in
 * applyGraphMutation, i.e. the mutation must not appear in unhandledMutations
 * after being applied to an empty state.
 *
 * See docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md.
 */

import { describe, expect, it } from "vitest";
import { MutationTypeSchema } from "./graphMutations";
import { applyGraphMutation } from "../state/graphMutationReducer";
import type { WorkflowRunState } from "@/lib/types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";

function emptyState(): WorkflowRunState {
  return {
    id: "run-test",
    name: "test",
    status: "running",
    tasks: new Map(),
    startedAt: new Date().toISOString(),
    completedAt: null,
    durationSeconds: null,
    finalScore: null,
    error: null,
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
    generations: [],
    resources: [],
    sandboxes: new Map(),
    threads: [],
    evaluations: new Map(),
  };
}

/**
 * Build a minimal synthetic mutation for a given mutation_type.
 * new_value contents must satisfy the schema for that type.
 */
function syntheticMutation(
  mutationType: string,
): DashboardGraphMutationData {
  const nodeId = "00000000-0000-0000-0000-000000000001";
  const newValueByType: Record<string, Record<string, unknown>> = {
    "node.added": {
      mutation_type: "node.added",
      task_key: "test-task",
      instance_key: "inst-1",
      description: "test",
      status: "pending",
      assigned_worker_key: null,
    },
    "node.removed": { mutation_type: "node.removed", status: "cancelled" },
    "node.status_changed": {
      mutation_type: "node.status_changed",
      status: "running",
    },
    "node.field_changed": {
      mutation_type: "node.field_changed",
      field: "description",
      value: "updated",
    },
    "edge.added": {
      mutation_type: "edge.added",
      source_node_id: nodeId,
      target_node_id: "00000000-0000-0000-0000-000000000002",
      status: "pending",
    },
    "edge.removed": { mutation_type: "edge.removed" },
    "edge.status_changed": {
      mutation_type: "edge.status_changed",
      status: "satisfied",
    },
    "annotation.set": {
      mutation_type: "annotation.set",
      namespace: "test",
      payload: {},
    },
    "annotation.deleted": {
      mutation_type: "annotation.deleted",
      namespace: "test",
      payload: {},
    },
  };

  return {
    run_id: "00000000-0000-0000-0000-000000000000",
    sequence: 1,
    mutation_type: mutationType as DashboardGraphMutationData["mutation_type"],
    target_type: "node",
    target_id: nodeId,
    actor: "test",
    new_value: newValueByType[mutationType] ?? {},
    old_value: null,
    reason: null,
    timestamp: new Date().toISOString(),
  };
}

const ALL_MUTATION_TYPES = MutationTypeSchema.options;

describe("graphMutationReducer — mutation-kind coverage", () => {
  it.each(ALL_MUTATION_TYPES)(
    "mutation_type '%s' is handled (does not fall through to unhandledMutations)",
    (mutationType) => {
      const state = emptyState();
      const mutation = syntheticMutation(mutationType);
      const next = applyGraphMutation(state, mutation);
      const unhandled = next.unhandledMutations ?? [];
      const fell = unhandled.some((u) => u.mutationType === mutationType);
      expect(fell).toBe(false);
    },
  );

  it("ALL_MUTATION_TYPES matches MutationTypeSchema.options (no stale snapshot)", () => {
    // This test fails if the schema drifts from the test's local snapshot.
    expect(ALL_MUTATION_TYPES).toEqual(MutationTypeSchema.options);
  });
});
```

### `tests/contract/__init__.py`

```python
# ergon/tests/contract/__init__.py
```

Empty — required for pytest discovery.

## Exact diffs for modified files

The only modification to existing files in this RFC is the `package.json`
`test:contracts` script already exists at
`ergon-dashboard/package.json` (`"test:contracts": "tsx --test tests/contracts/contracts.test.ts"`).
No changes needed there; the frontend test file uses `describe`/`it` from vitest,
so the invocation command must be updated to use vitest instead of the node test
runner used by the existing `contracts.test.ts`.

```diff
--- a/ergon-dashboard/package.json
+++ b/ergon-dashboard/package.json
@@ ... scripts section ...
-    "test:contracts": "tsx --test tests/contracts/contracts.test.ts",
+    "test:contracts": "vitest run tests/contracts/ tests/graph/",
```

**Note:** The existing `tests/contracts/contracts.test.ts` uses the Node built-in
test runner (`import test from "node:test"`), not vitest. The new
`graphMutations.test.ts` uses vitest. Both can coexist if `test:contracts` is
split or if the existing test is migrated to vitest. The simplest change is to
run them with separate commands:

```diff
--- a/ergon-dashboard/package.json
+++ b/ergon-dashboard/package.json
@@ ... scripts ...
-    "test:contracts": "tsx --test tests/contracts/contracts.test.ts",
+    "test:contracts": "tsx --test tests/contracts/contracts.test.ts && vitest run tests/graph/",
```

Alternatively, migrate `contracts.test.ts` to vitest entirely (out of scope for
this RFC). For now the diff above is the minimal change.

The backend test lives in a new `tests/contract/` directory (note: singular, to
distinguish from the `ergon-dashboard/tests/contracts/` directory). No changes
to existing Python files are required.

## Package structure

```
ergon/
  tests/
    contract/               ← NEW directory
      __init__.py           ← NEW (empty)
      test_dashboard_emitter_wiring.py  ← NEW

  ergon-dashboard/
    src/
      features/graph/
        contracts/
          graphMutations.test.ts  ← NEW
```

The `tests/contract/` directory sits alongside `tests/state/` and
`tests/integration/`. It is a pytest-discovered package; `__init__.py` is
required because other test packages under `tests/` have it.

## Implementation order

| Step | What | Files touched | PR |
|---|---|---|---|
| **1** | Land the per-method wiring fix for the 9 dead emitter methods (`docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md`). Without this, the contract test is red on arrival. | `ergon_core/ergon_core/core/runtime/inngest/start_workflow.py`, `complete_workflow.py`, `task_management_service.py`, `evaluate_task_run.py`, `cleanup_cancelled_task.py`, and wherever `resource_published` and `thread_message_created` belong | PR 1 — bug fix |
| **2** | Create `tests/contract/__init__.py` and `tests/contract/test_dashboard_emitter_wiring.py` | ADD 2 files | PR 2 — contract test |
| **3** | Verify the backend contract test is green locally (`uv run pytest tests/contract -v`), then add `tests/contract` to the `test:be:state` invocation in `package.json` | MODIFY `package.json` | PR 2 |
| **4** | Create `ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts` | ADD 1 file | PR 3 — FE contract test |
| **5** | Update `ergon-dashboard/package.json` `test:contracts` script to include vitest for the new test | MODIFY `ergon-dashboard/package.json` | PR 3 |
| **6** | Update `docs/architecture/05_dashboard.md#invariants` to cite the contract tests; add emitter coverage table inline | MODIFY `docs/architecture/05_dashboard.md` | PR 2 or PR 3 (alongside whichever closes last) |

Steps 2–3 and 4–5 are independent and can land in parallel PRs once Step 1 is
merged.

## File map

### ADD

| File | Purpose |
|---|---|
| `ergon/tests/contract/__init__.py` | Empty init; required for pytest discovery of the new `contract/` package |
| `ergon/tests/contract/test_dashboard_emitter_wiring.py` | Backend contract test: enumerates `DashboardEmitter` public methods via `inspect` and asserts each has at least one call site in the runtime packages |
| `ergon/ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts` | Frontend coverage test: asserts every `MutationType` variant in `MutationTypeSchema` is handled by `applyGraphMutation` without falling through to `unhandledMutations` |

### MODIFY

| File | Change |
|---|---|
| `ergon/ergon-dashboard/package.json` | Extend `test:contracts` script to invoke vitest for the new TS test file |
| `ergon/docs/architecture/05_dashboard.md` | Update `#invariants` section to cite the two new contract tests; add emitter-method coverage table |

**Note:** `package.json` (repo root) does not need modification if `test:be:state`
already runs all `tests/state/` content. The `tests/contract/` directory must be
added to the pytest invocation explicitly if `test:be:state` uses a directory
glob rather than `discover`. Check `pnpm run test:be:state` in `package.json`:

```json
"test:be:state": "uv run pytest tests/state -q"
```

This targets `tests/state/` explicitly. The contract tests must be added either
by changing the command to `uv run pytest tests/state tests/contract -q` or by
adding a dedicated `test:be:contract` script. The simpler path is:

```diff
-    "test:be:state": "uv run pytest tests/state -q",
+    "test:be:state": "uv run pytest tests/state tests/contract -q",
```

This is also a MODIFY to `package.json` (repo root).

Updated MODIFY table:

| File | Change |
|---|---|
| `ergon/package.json` | Add `tests/contract` to `test:be:state` pytest invocation |
| `ergon/ergon-dashboard/package.json` | Extend `test:contracts` script to include vitest for new TS test |
| `ergon/docs/architecture/05_dashboard.md` | Update invariants section + add emitter coverage table |

## Testing approach

### Unit / state tests (backend)

The contract test itself is both unit and contract:

- `test_no_unwired_methods` — runs the full scan; intended to be the CI gate.
  In isolation it is fast (pure filesystem + regex, no DB, no Inngest).
- `test_method_is_async` — parametrized over all methods; guards against async
  regression.
- `test_exempt_methods_still_exist` — guards against stale `_EXEMPT_METHODS`
  if a method is renamed.

Representative invocation:

```bash
uv run pytest tests/contract/test_dashboard_emitter_wiring.py -v
```

Expected passing output (post bug fix):

```
PASSED tests/contract/test_dashboard_emitter_wiring.py::TestDashboardEmitterWiring::test_no_unwired_methods
PASSED tests/contract/test_dashboard_emitter_wiring.py::TestDashboardEmitterWiring::test_exempt_methods_still_exist
PASSED tests/contract/test_dashboard_emitter_wiring.py::TestDashboardEmitterWiring::test_method_is_async[workflow_started]
PASSED tests/contract/test_dashboard_emitter_wiring.py::TestDashboardEmitterWiring::test_method_is_async[workflow_completed]
...
```

Expected failing output (before bug fix or after adding an unwired method):

```
FAILED tests/contract/test_dashboard_emitter_wiring.py::TestDashboardEmitterWiring::test_no_unwired_methods
  DashboardEmitter methods with zero call sites in ergon_core/, ergon_builtins/, ergon_infra/:
    - task_status_changed
    - workflow_started
    ...
  For each method, add a call site at the point of the corresponding state mutation.
  See: docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md
       docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md
```

### Integration tests

No integration tests are added by this RFC. The contract test is deliberately
free of I/O so it runs in `test:be:fast`. The wiring itself (calling the emitter
from the right place) is exercised by the existing state and integration tests
once the bug fix lands.

### Frontend contract test

```bash
pnpm -C ergon-dashboard run test:contracts
```

Uses vitest with `it.each` over `MutationTypeSchema.options`. Any new variant
added to `MutationTypeSchema` without a handler in `applyGraphMutation` causes:

```
FAIL  src/features/graph/contracts/graphMutations.test.ts
  ✗ mutation_type 'new.kind' is handled (does not fall through to unhandledMutations)
    AssertionError: expected true to be false
```

### Coverage of all 12 emitter methods

The contract test verifies method-level wiring. Individual method correctness
(correct arguments at the right moment) is covered by existing state tests once
the bug-fix PR lands:

- `workflow_started` / `workflow_completed` — `test_workflow_finalization.py`
- `task_status_changed` — `test_graph_repository.py`, `test_plan_subtasks.py`
- `task_evaluation_updated` — `test_type_invariants.py`
- `task_cancelled` — `test_subtask_cancellation_service.py`
- `graph_mutation` / `on_context_event` — `test_graph_mutation_listener.py`,
  `test_context_event_repository.py`

## Trace / observability impact

No new spans, metrics, or log lines. The contract test runs offline; it touches
no Inngest client or trace sink. The architecture doc update (Step 6) adds the
emitter coverage table as a developer-visible artifact — no runtime change.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Contract test runs before the bug-fix PR merges | Test is red in CI on first merge | Sequence: land bug-fix PR first, then the contract test PR. CI pipeline enforces ordering via PR dependencies or manual gating. |
| `inspect.getmembers` misses dynamically-added methods | Silent gap in coverage | All `DashboardEmitter` methods are statically defined; no `__getattr__` or dynamic method addition. Acceptable risk. |
| Regex scan produces false positives (e.g. a comment containing `.workflow_started(`) | Method counted as wired when it is not | False positives would cause the test to *not* fail when it should. Acceptable — the test is a floor, not a proof. Code review remains the correctness gate; the test catches complete blindness. |
| `_EXEMPT_METHODS` grows silently | New methods added to the exempt list with no justification | `test_exempt_methods_still_exist` ensures all exempt methods still exist; but it does not prevent adding new entries. Reviewed in PR. |
| TS test uses `vitest` but existing `contracts.test.ts` uses node test runner | `test:contracts` command conflict | Split the commands or migrate the existing test to vitest in the same PR. Explicit note in Implementation Order Step 5. |
| Frontend test checks `unhandledMutations` presence but that field is optional on `WorkflowRunState` | Test false-negative if field is undefined | `const unhandled = next.unhandledMutations ?? []` — the `?? []` default is in the test; safe. |
| Sandbox emitter methods remain wired only through `DashboardEmitterSandboxEventSink`, which has no constructor site | Three methods stay effectively dead at runtime | Tracked separately as `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md`. The contract test exempts them explicitly with a comment explaining the separate tracker. |

## Invariants affected

From `docs/architecture/05_dashboard.md#invariants`:

> Every persistent backend state change on a wired surface must have a
> corresponding `dashboard/*` event; a state change without an emit is a bug
> in the emitter layer. **Enforcement is not automated today (see Follow-ups).**

This RFC replaces "Enforcement is not automated today" with machine enforcement.
The updated invariant text (to be applied in Step 6):

> Every persistent backend state change on a wired surface must have a
> corresponding `dashboard/*` event. A `DashboardEmitter` method with zero
> call sites in `ergon_core/`, `ergon_builtins/`, or `ergon_infra/` fails
> `pnpm run test:be:fast` via `tests/contract/test_dashboard_emitter_wiring.py`.
> A `RunGraphMutation.kind` with no frontend reducer branch fails
> `pnpm -C ergon-dashboard run test:contracts` via
> `src/features/graph/contracts/graphMutations.test.ts`.

No other invariants are changed. The "emitter calls are best-effort" and
"DashboardStore is a cache" invariants are untouched.

## Alternatives considered

- **Review-only discipline.** Status quo; has demonstrably failed — 9 of 12
  methods were dead for an unknown period before discovery via grep.
- **Runtime assertion on first emit.** Rejected: false positives on emitter
  paths that are legitimately quiescent during a given run (e.g. a run with
  zero sandboxes would never trigger `sandbox_created`), and fails-open in
  tests that don't exercise the path.
- **Type-level encoding (requiring each method to be referenced at compile
  time via a sentinel).** Rejected: more invasive than a pytest, and Python's
  import graph doesn't give useful reachability without extra machinery.
- **AST-based scan instead of regex.** More robust (no false positives from
  comments); considerably more implementation complexity for marginal gain.
  The regex approach is acceptable because false positives cause the test to
  pass when it should fail (not fail when it should pass), and code review
  remains the correctness gate.
- **Generated emitter-coverage table as a separate file.** Inline table in
  `05_dashboard.md` preferred: one fewer file, no separate sync step, stays
  under ~30 rows per the open-question resolution below.

## Open questions

- Should the backend test tolerate listener-style wiring
  (`repo.add_listener(emitter.foo)`) as proof-of-wiring, or require a
  direct call site? **Resolution:** Allow both. The pattern list is
  `\.{name}\(` OR `add_listener\(.*\.{name}\b` OR
  `add_mutation_listener\(.*\.{name}\b`. The current wiring of
  `graph_mutation` and `on_context_event` uses listener registration; both
  patterns are required for the test to pass without exempting them.
- Where should the generated emitter-coverage table live — inline in
  `05_dashboard.md` or a sibling `05_dashboard_emitter_coverage.md`?
  **Resolution:** Inline in `05_dashboard.md`. 12 emitter methods fit well
  under the 30-row threshold; a sibling file adds navigation friction without
  benefit.

## On acceptance

When this RFC moves from `active/` to `accepted/`:
- Update `docs/architecture/05_dashboard.md#invariants` to cite the contract
  tests (per Implementation Order Step 6).
- Close `docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md`
  once the bug-fix PR (Step 1) lands and the contract test is green.
- No separate plan file is needed — the implementation order table above is
  the plan.
