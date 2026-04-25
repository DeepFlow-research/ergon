# E2E Contract And Playwright Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make E2E tests prove the real product path from PostgreSQL persistence through repository/read-service/API DTOs into the dashboard UI.

**Architecture:** Move smoke assertions upward from ad hoc SQL toward repository/read-service contracts, while keeping narrow storage-level checks only where the behavior being tested is explicitly storage-level. Expand live Playwright smoke coverage so real PG-backed runs are clicked, inspected, and asserted in the frontend rather than only screenshotted after `graph-canvas` appears.

**Tech Stack:** Python `pytest`, SQLModel repositories/read services, FastAPI test harness endpoints, Next.js dashboard, Playwright, TypeScript contract parsers.

---

## Current Findings

The Python smoke tests are deep but mostly direct-SQL. They assert graph shape, resource rows, context-event counts, sandbox WAL/lifecycle rows, thread ordering, blob roundtrips, temporal ordering, cohort membership, and evaluation rows. That is useful for persistence regression, but it can miss bugs where data exists in PostgreSQL and is then dropped or reshaped incorrectly by repository/read-service/API layers.

The live Playwright smoke tests are too shallow for the current dashboard. `ergon-dashboard/tests/e2e/_shared/smoke.ts` validates a reduced backend harness DTO, navigates to the run page, checks `graph-canvas`, and captures screenshots. The dashboard now exposes richer `data-testid` hooks for graph nodes, workspace panels, event stream, timeline, status counts, and cohort run rows, so the E2Es should assert those real UI surfaces.

The seeded dashboard tests cover richer UI interactions, but against synthetic dashboard harness fixtures rather than real smoke runs from PG. They are still valuable, but they do not prove real persisted data hydrates into the frontend.

There is one semantic decision before implementation: task-level evaluations for dynamic subtasks currently do not appear in `RunSnapshotDto.evaluations_by_task`, because `RunTaskEvaluation` stores `definition_task_id`, while dynamic subtask nodes are runtime `RunGraphNode` rows that may not map to an `ExperimentDefinitionTask`.

## Semantic Decision: Dynamic Leaf Evaluations

Today, `RunTaskEvaluation` has:

- `run_id`
- `definition_task_id`
- `definition_evaluator_id`
- score/pass/failure summary fields

`RunReadService.build_run_snapshot()` builds a `defn_to_node` map from static definition task IDs to run graph node IDs, then `_task_keyed_evaluations()` attaches evaluations to frontend task IDs through that map. If an evaluation's `definition_task_id` does not map to a node, the code skips it. The comment says dynamic-task evaluation would need a `node_id` foreign key.

This means:

- The run-level final score can still appear, because it is averaged from all evaluation rows.
- Static definition task evaluations can appear in `evaluations_by_task`.
- Dynamic subtask evaluations cannot reliably appear in `evaluations_by_task` unless the evaluation row also records the runtime node ID or execution ID.

My recommendation:

- **Run-level benchmark/evaluator results should appear at the run level.** They answer “did this run pass the benchmark?”
- **Task-level evaluations should appear in the task workspace only when they are genuinely about that task node.**
- **Dynamic leaf evaluations should appear in the frontend if we evaluate dynamic leaves individually.** To support that correctly, add `node_id` and preferably `task_execution_id` to `RunTaskEvaluation`, then key `evaluations_by_task` by runtime node ID.
- **Do not fake dynamic task evaluations by guessing through `definition_task_id`.** That would hide the actual model mismatch and make E2Es less trustworthy.

Implementation can proceed in two phases: first harden E2Es around the current behavior, then add dynamic-task evaluation mapping if we decide task workspaces should show those evaluations.

## File Structure

### Backend E2E Assertion Layer

- `tests/e2e/_asserts.py`: Replace most direct SQL assertions with assertions over `RunReadService.build_run_snapshot()`, `RunReadService.list_mutations()`, and existing query/repository APIs.
- `tests/e2e/_read_contracts.py`: New focused helper module for fetching and asserting read-service DTOs in tests.
- `tests/e2e/test_researchrubrics_smoke.py`: Keep environment-specific artifact content checks and route shared assertions through the new helper layer.
- `tests/e2e/test_minif2f_smoke.py`: Add out-of-band MiniF2F artifact checks.
- `tests/e2e/test_swebench_smoke.py`: Add out-of-band SWE-Bench artifact checks.

### Backend API/Test Harness

- `ergon_core/ergon_core/core/api/test_harness.py`: Expand the live Playwright harness DTO with node IDs and the omitted `executions`, `mutations`, and per-task counts that Playwright will assert.
- `ergon_core/ergon_core/core/api/runs.py`: No broad refactor. Only change if dynamic evaluation semantics are explicitly approved.
- `ergon_core/ergon_core/core/runtime/services/run_read_service.py`: Use existing snapshot behavior for read-service assertions. Only change for dynamic evaluation mapping if approved.
- Potential migration: add `node_id` / `task_execution_id` to `RunTaskEvaluation` only if we choose dynamic task evaluation UI support.

### Frontend E2E

- `ergon-dashboard/tests/helpers/backendHarnessClient.ts`: Update `BackendRunState` to match the backend harness DTO exactly.
- `ergon-dashboard/tests/e2e/_shared/smoke.ts`: Assert the real live UI path: cohort route, run header, graph node selection, workspace panels, status counts, event stream, timeline, screenshots.
- `ergon-dashboard/tests/e2e/_shared/expected.ts`: Keep as the TS topology mirror for now, but add a drift test.
- `ergon-dashboard/tests/e2e/run.snapshot.spec.ts` and `run.delta.spec.ts`: Keep seeded UI tests; do not replace them with live tests.

## Task 1: Add Read-Service Contract Helpers

**Files:**

- Create: `tests/e2e/_read_contracts.py`
- Modify: `tests/e2e/_asserts.py`

- [x] **Step 1: Create a helper for required run snapshots**

Create `tests/e2e/_read_contracts.py`:

```python
from __future__ import annotations

from uuid import UUID

from ergon_core.core.api.schemas import RunSnapshotDto
from ergon_core.core.runtime.services.run_read_service import RunReadService


def require_run_snapshot(run_id: UUID) -> RunSnapshotDto:
    snapshot = RunReadService().build_run_snapshot(run_id)
    assert snapshot is not None, f"RunReadService returned no snapshot for run {run_id}"
    return snapshot
```

- [x] **Step 2: Add snapshot-backed graph assertions**

In `tests/e2e/_asserts.py`, rewrite `_assert_run_graph()` to assert over `snapshot.tasks`, `snapshot.root_task_id`, `snapshot.total_tasks`, `snapshot.total_leaf_tasks`, and dependency IDs. Keep a tiny direct graph repository check only if the read-service DTO cannot express a needed edge invariant.

- [x] **Step 3: Add snapshot-backed resources/executions/evaluations/thread assertions**

Rewrite these functions to use the snapshot first:

- `_assert_run_resources`
- `_assert_run_turn_counts`
- `_assert_thread_messages_ordered`
- `_assert_run_evaluation`

Keep `_assert_blob_roundtrip()` as storage-level because it intentionally proves blob bytes exist on disk and are stable across reads.

- [x] **Step 4: Keep WAL/lifecycle checks explicit until repository methods exist**

For `SandboxCommandWalEntry` and `SandboxEvent`, either use existing repository methods if available or leave the direct SQL in place with a comment explaining that these are storage-level observability checks pending a read-service API.

- [x] **Step 5: Verify focused Python E2E helpers**

Run:

```bash
uv run ruff check tests/e2e/_asserts.py tests/e2e/_read_contracts.py
uv run pytest tests/e2e/test_researchrubrics_smoke.py -v --timeout=330
```

Expected: the helper-level assertions pass or reveal a real read-service/API gap where direct SQL previously passed.

## Task 2: Resolve Sad-Path Semantics

**Files:**

- Modify: `tests/e2e/_asserts.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/workers/researchrubrics_smoke_sadpath.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/leaf_base.py`

- [x] **Step 1: Confirm actual sad-path behavior from current runtime code**

Run:

```bash
uv run pytest tests/e2e/test_researchrubrics_smoke.py -v --timeout=330
```

Inspect the sad run graph statuses and thread count through the test failure/output or a short one-off query using the existing test harness endpoint.

- [x] **Step 2: Pick one intended behavior**

Chosen behavior:

2. **Score-zero completion semantics:** all leaves complete, `l_2` produces score-zero output, `l_3` still runs, and the smoke-completion thread has 8 messages because only `l_2` suppresses completion.

Do not keep comments and tests split across both meanings.

- [x] **Step 3: Update tests and comments to match the chosen behavior**

Updated stale comments in the sad-path worker, leaf base, and temporal-ordering
assertion. Existing E2E assertions already encoded score-zero semantics:
all leaves completed, 8 completion-thread messages, one partial artifact, and
run evaluation score 0.

## Task 3: Expand The Backend Harness DTO

**Files:**

- Modify: `ergon_core/ergon_core/core/api/test_harness.py`
- Modify: `ergon-dashboard/tests/helpers/backendHarnessClient.ts`

- [x] **Step 1: Add node IDs and counts to the backend DTO**

Extend `TestGraphNodeDto` with:

```python
id: UUID
parent_node_id: UUID | None
```

Extend `TestRunStateDto` with fields Playwright will assert:

```python
execution_count: int
mutation_count: int
resource_count: int
thread_count: int
context_event_count: int
```

If per-task counts are straightforward to compute, include them keyed by `task_slug` or node ID.

- [x] **Step 2: Update the TS harness type**

In `ergon-dashboard/tests/helpers/backendHarnessClient.ts`, update `BackendRunState` to include every backend DTO field, especially `executions`, which is currently omitted.

- [x] **Step 3: Add a narrow backend unit/API test if one exists nearby**

If there is an existing test harness API test, add assertions that `read_run_state` includes the new fields. If not, rely on live E2E coverage in Task 4 and keep this change small.

## Task 4: Add Real Live Playwright Assertions

**Files:**

- Modify: `ergon-dashboard/tests/e2e/_shared/smoke.ts`
- Possibly create: `ergon-dashboard/tests/e2e/_shared/liveRunAssertions.ts`

- [x] **Step 1: Assert the expanded backend DTO**

For happy runs, assert:

```ts
expect(state.status).toBe("completed");
expect(state.graph_nodes.length).toBe(10);
expect(state.resource_count).toBeGreaterThanOrEqual(18);
expect(state.mutations.length).toBeGreaterThan(0);
expect(state.executions.length).toBeGreaterThan(0);
expect(state.evaluations.some((e) => e.score === 1.0)).toBe(true);
```

For sad runs, assert the chosen sad-path semantics from Task 2.

- [x] **Step 2: Navigate through the cohort-aware route**

Use:

```ts
const cohortId = await client.getCohortId(cohortKey);
await page.goto(`/cohorts/${cohortId}/runs/${run_id}`);
```

This validates breadcrumb context and the same route users reach from the cohort detail page.

- [x] **Step 3: Assert run header and status UI**

Assert:

- `run-header` is visible
- status text is completed
- score is visible when expected
- `run-status-bar` and relevant `run-status-count-*` chips exist

- [x] **Step 4: Click a real graph node**

Pick a stable leaf node from the backend DTO, preferably `d_root` or another completed leaf:

```ts
const leaf = state.graph_nodes.find((n) => n.task_slug === "d_root");
expect(leaf).toBeTruthy();
await page.getByTestId(`graph-node-${leaf!.id}`).click();
```

- [x] **Step 5: Assert workspace sections against live data**

After clicking the node, assert:

- `workspace-header`
- `workspace-actions`
- `workspace-outputs`
- `workspace-executions`
- `workspace-sandbox`
- `workspace-communication`
- `workspace-transitions`

Only assert `workspace-evaluation` content if the selected node actually has a task-level evaluation in the snapshot. Do not force dynamic-leaf evaluation visibility until the semantic decision is implemented.

- [x] **Step 6: Assert event stream and timeline**

Click `event-stream-toggle`, assert `event-stream-region` and one or more `event-row-*` entries. Switch to timeline mode and assert `timeline-region` when mutations exist.

- [x] **Step 7: Capture screenshots after assertions**

Keep the screenshot filenames based on real run IDs:

```ts
path.join(screenshotDir, cfg.env, `${run_id}-${kind}.png`)
```

The screenshots should now represent a validated UI state, not just a loaded canvas.

## Task 5: Add Benchmark-Specific Out-Of-Band Artifact Checks

**Files:**

- Modify: `tests/e2e/test_minif2f_smoke.py`
- Modify: `tests/e2e/test_swebench_smoke.py`

- [x] **Step 1: Add MiniF2F artifact verification**

Add an out-of-band check like ResearchRubrics:

- 9 `proof_*.lean` resources
- file content includes `theorem smoke_trivial`
- file content includes `:=`

- [x] **Step 2: Add SWE-Bench artifact verification**

Add:

- 9 `patch_*.py` resources
- file parses as Python AST
- a function named `add` exists

- [x] **Step 3: Keep criteria checks as in-workflow checks**

Do not remove criterion checks. The E2E out-of-band checks intentionally catch silent criterion regressions or missing evaluation dispatch.

## Task 6: Prevent Python/TypeScript Topology Drift

**Files:**

- Modify: `ergon-dashboard/tests/e2e/_shared/expected.ts`
- Add or modify: `tests/unit/...` drift test location to be selected during implementation

- [x] **Step 1: Add a drift test**

Create a small unit test that compares:

- Python `EXPECTED_SUBTASK_SLUGS`
- TS `EXPECTED_SUBTASK_SLUGS`

Use a simple parser or emit a JSON file during test setup. Avoid adding a generation pipeline unless drift becomes frequent.

- [x] **Step 2: Keep the TS mirror for Playwright**

Do not add cross-language runtime imports to Playwright. The mirror is acceptable if drift is tested.

## Task 7: Dynamic Evaluation Mapping

Approved: dynamic task-level evaluations should render by runtime graph node ID,
not by static definition task ID.

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Add migration under `ergon_core/migrations/versions/`
- Modify: evaluation persistence call sites
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/run_read_service.py`
- Modify: frontend types/contracts if task-level dynamic evaluations become visible

- [x] **Step 1: Add runtime node references to evaluations**

Add required runtime identity fields:

```python
node_id: UUID
task_execution_id: UUID
```

Keep `definition_task_id` nullable as static provenance only; dynamic nodes may not
have a static definition task row. The migration backfills existing rows from task
executions and drops rows that cannot be truthfully mapped to a runtime node.

- [x] **Step 2: Persist node/execution IDs when evaluation is task-specific**

Update evaluation dispatch/persistence so task-specific evaluator results record the runtime node and execution IDs.

- [x] **Step 3: Key `_task_keyed_evaluations()` by `node_id`**

In `ergon_core/core/api/runs.py`, key evaluations by `node_id`. Do not guess from
`definition_task_id`; evaluation rows without runtime identity are not truthfully
renderable in a task workspace.

- [x] **Step 4: Add frontend assertions**

Once dynamic evaluations are correctly keyed, live Playwright can assert `workspace-evaluation` content after clicking evaluated dynamic leaves.

## Verification Plan

Run focused Python checks:

```bash
uv run ruff check tests/e2e ergon_core/ergon_core/core/api/test_harness.py
uv run pytest tests/e2e/test_researchrubrics_smoke.py -v --timeout=330
uv run pytest tests/e2e/test_minif2f_smoke.py -v --timeout=330
uv run pytest tests/e2e/test_swebench_smoke.py -v --timeout=330
```

Run focused frontend checks:

```bash
pnpm --dir ergon-dashboard exec playwright test tests/e2e/*.smoke.spec.ts --project=chromium
pnpm --dir ergon-dashboard test
pnpm --dir ergon-dashboard lint
```

Run CI-level validation:

```bash
gh pr checks
gh run list --branch "$(git branch --show-current)" --limit 10
```

After CI E2E completes, verify the screenshots ref contains PNGs:

```bash
hash=$(git ls-remote https://github.com/DeepFlow-research/ergon.git refs/heads/screenshots/pr-<PR_NUMBER> | awk '{print $1}')
git fetch origin "$hash"
git ls-tree -r --name-only "$hash"
```

Expected: each smoke env has `*.png`, not only `EMPTY.txt`.

## Recommended Execution Order

1. Task 2: resolve sad-path semantics before encoding stronger assertions.
2. Task 1: move Python assertions to read-service contracts.
3. Task 3: expand backend harness DTO.
4. Task 4: add real live Playwright assertions.
5. Task 5: add benchmark-specific out-of-band checks.
6. Task 6: add topology drift guard.
7. Task 7 only if we decide dynamic task evaluations should appear in the FE.
