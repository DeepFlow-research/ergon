# Dashboard Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay down dashboard frontend debt by making wire contracts, server harness/backend reads, dashboard store state, and UI state explicit and testable.

**Architecture:** Keep visual components mostly intact. Refactor the dashboard at its boundaries: REST/socket payloads enter through parsers, convert once into dashboard domain state, update through shared reducers, and serialize back through a single wire serializer. Server components and API route handlers should use one server-side data adapter so harness fallback behavior is consistent.

**Tech Stack:** Next.js 14 App Router, TypeScript, Zod, Socket.io, Playwright, Node test runner via `tsx --test`, existing generated OpenAPI/event contracts.

---

## Non-Goals

- Do not redesign the dashboard UI.
- Do not replace Socket.io.
- Do not remove the dashboard test harness.
- Do not reintroduce deleted backend env-var gates.
- Do not preserve compatibility with stale dashboard fixture payloads; update fixtures to the current generated contract.

## Clean Result Folder Layout

The final dashboard boundary code should be organized as follows:

```text
ergon-dashboard/
  src/
    app/
      api/
        cohorts/
          route.ts                         # thin route handler, delegates to server-data adapter
          [cohortId]/route.ts              # thin route handler, delegates to server-data adapter
        danger/
          test-harness/dashboard/          # dashboard-only harness routes; Next cannot route __danger__ folders
        experiments/[experimentId]/page.tsx # uses server-data adapter, no bespoke harness fallback
        run/[runId]/page.tsx                # uses server-data adapter
        cohorts/[cohortId]/page.tsx         # uses server-data adapter
        cohorts/[cohortId]/runs/[runId]/page.tsx # uses server-data adapter
    lib/
      contracts/
        rest.ts                            # generated REST parser wrappers only
        events.ts                          # generated/socket parser wrappers only
        contextEvents.ts                   # UI/domain context event payload types
      run-state/
        domain.ts                          # dashboard domain/store types, if moved out of lib/types.ts
        hydrate.ts                         # wire RunSnapshot -> WorkflowRunState
        serialize.ts                       # WorkflowRunState -> wire RunSnapshot
        contextEvents.ts                   # context part/event_type conversions
        reducers.ts                        # pure run-state reducers shared by store + client hook
        metrics.ts                         # run/task metric recalculation
        index.ts                           # public run-state boundary exports
      server-data/
        fetchBackend.ts                    # fetchErgonApi wrapper + status/timeout policy
        harness.ts                         # read-only harness access helpers
        runs.ts                            # loadRunSnapshot/loadRunPageData
        cohorts.ts                         # loadCohortDetail/loadCohortList/updateCohortStatus
        experiments.ts                     # loadExperimentDetail/loadExperimentList
        responses.ts                       # NextResponse helpers for API routes
      testing/
        dashboardHarness.ts                # in-memory harness implementation; server-only
      state/
        store.ts                           # thin singleton store using run-state reducers
      socket/
        server.ts                          # socket rooms/broadcasts only
    hooks/
      useRunState.ts                       # client socket subscription + reducer dispatch
    components/
      run/
        RunWorkspacePage.tsx               # orchestration shell only
        useRunDisplayState.ts              # extracted after boundary work
        useRunKeyboardShortcuts.ts         # extracted after boundary work
        useRunPanelLayout.ts               # extracted after boundary work
  tests/
    contracts/
      rest.contract.test.ts
      run-state-roundtrip.contract.test.ts
      context-events.contract.test.ts
      server-data.contract.test.ts
    e2e/
      ...
```

Do not create this whole tree in one mechanical move. Create files only when a task needs them. The important ownership rule is:

```text
generated/rest/events -> contract wrappers -> run-state/server-data boundary -> UI/store/hooks
```

No component should parse backend DTOs directly. No route/page should hand-roll harness fallback.

## Mental Model

The dashboard should have three explicit shapes:

```text
WireRunSnapshot      # parsed backend/API payload, generated-contract shaped
WorkflowRunState     # dashboard runtime/store state with Maps, history, edges, annotations
RunDisplayState      # UI-selected state, maybe live or replay snapshot
```

Data flow:

```text
FastAPI / dashboard harness / socket sync
        ↓
contract parser
        ↓
hydrateRunSnapshot()
        ↓
WorkflowRunState
        ↓
reducers for live updates
        ↓
RunWorkspacePage / TaskWorkspace / graph/activity UI
```

When state leaves the dashboard store over REST or socket sync:

```text
WorkflowRunState
        ↓
serializeRunSnapshot()
        ↓
WireRunSnapshot
        ↓
parseRunSnapshot() round-trip test must pass
```

## Route Naming Constraint

Backend danger harness routes intentionally use:

```text
/api/__danger__/test-harness/...
```

The Next.js dashboard must not use an app directory named `__danger__`, because underscore-prefixed App Router segments are treated as private and do not route. Dashboard-only harness routes should stay at:

```text
/api/danger/test-harness/dashboard/...
```

Document this in route comments and tests so a future cleanup does not move them back to `__danger__`.

## Task 1: Wire Existing Frontend Tests Into One Reliable Fast Path

**Files:**
- Modify: `ergon-dashboard/package.json`
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `ergon-dashboard/tests/e2e/health.spec.ts`
- Test: all existing dashboard `*.test.ts` files

- [ ] **Step 1: Add a unit test script that runs all non-Playwright Node tests**

In `ergon-dashboard/package.json`, replace the narrow contract script with explicit fast scripts:

```json
{
  "scripts": {
    "test:unit": "tsx --test \"src/**/*.test.ts\" \"tests/**/*.test.ts\"",
    "test:contracts": "tsx --test tests/contracts/contracts.test.ts src/features/graph/contracts/graphMutations.test.ts",
    "test": "pnpm run test:unit"
  }
}
```

If `test:unit` accidentally includes Playwright specs, narrow it to:

```json
"test:unit": "tsx --test \"src/**/*.test.ts\" \"tests/contracts/**/*.test.ts\" \"tests/graph/**/*.test.ts\""
```

- [ ] **Step 2: Verify the unit script catches currently orphaned tests**

Run:

```bash
pnpm -C ergon-dashboard run test:unit
```

Expected: all Node test files run, including:

```text
src/app/api/health/health.test.ts
src/features/activity/*.test.ts
src/features/evaluation/selectors.test.ts
src/hooks/useRunState.socketHydration.test.ts
src/lib/timeFormat.test.ts
src/components/workspace/filterTaskEvidenceForTime.test.ts
tests/contracts/contracts.test.ts
tests/graph/taskTiming.test.ts
```

- [ ] **Step 3: Align health e2e with Playwright baseURL**

In `ergon-dashboard/tests/e2e/health.spec.ts`, remove the hardcoded `BASE` constant and use relative URLs:

```ts
test("returns 200 with healthy status when build is fresh", async ({ request }) => {
  const res = await request.get("/api/health");
  expect(res.status()).toBe(200);
});
```

For page navigation:

```ts
await page.goto("/");
await expect(page.locator('[data-testid="build-health-toast"]')).not.toBeVisible();
```

Avoid `networkidle`; wait for the specific DOM state instead.

- [ ] **Step 4: Add frontend tests to CI fast**

In `.github/workflows/ci-fast.yml`, after TypeScript check:

```yaml
      - name: Frontend unit tests
        run: pnpm -C ergon-dashboard run test:unit

      - name: Install Playwright browsers
        run: pnpm -C ergon-dashboard exec playwright install --with-deps chromium

      - name: Dashboard harness e2e
        env:
          ERGON_API_BASE_URL: http://127.0.0.1:9000
        run: pnpm -C ergon-dashboard run e2e
```

If the e2e job is too slow for the lint/typecheck job, split it into a separate `frontend-e2e` job that `needs: frontend-checks`.

- [ ] **Step 5: Verify**

Run:

```bash
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run e2e
pnpm -C ergon-dashboard run typecheck
pnpm -C ergon-dashboard run lint
```

Expected:

```text
unit tests pass
20 local dashboard e2e pass, live smoke specs skip without live env
typecheck passes
lint passes
```

## Task 2: Split Wire Run Snapshot From Dashboard Runtime State

**Files:**
- Create: `ergon-dashboard/src/lib/run-state/domain.ts`
- Create: `ergon-dashboard/src/lib/run-state/hydrate.ts`
- Create: `ergon-dashboard/src/lib/run-state/serialize.ts`
- Create: `ergon-dashboard/src/lib/run-state/contextEvents.ts`
- Create: `ergon-dashboard/src/lib/run-state/index.ts`
- Modify: `ergon-dashboard/src/lib/runState.ts` (temporary compatibility re-export)
- Modify: `ergon-dashboard/src/lib/types.ts`
- Test: `ergon-dashboard/tests/contracts/run-state-roundtrip.contract.test.ts`

- [ ] **Step 1: Write the failing round-trip test**

Create `ergon-dashboard/tests/contracts/run-state-roundtrip.contract.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { parseRunSnapshot } from "../../src/lib/contracts/rest";
import { hydrateRunSnapshot, serializeRunSnapshot } from "../../src/lib/run-state";
import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";

test("run state serializes back into a valid wire run snapshot", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const state = hydrateRunSnapshot(run);
  const wire = serializeRunSnapshot(state);
  const reparsed = parseRunSnapshot(wire);

  assert.equal(reparsed.id, FIXTURE_IDS.runId);
  assert.equal(reparsed.tasks[FIXTURE_IDS.solveTaskId]?.id, FIXTURE_IDS.solveTaskId);
});
```

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test tests/contracts/run-state-roundtrip.contract.test.ts
```

Expected: FAIL because `src/lib/run-state` does not exist yet.

- [ ] **Step 2: Create domain exports**

Create `ergon-dashboard/src/lib/run-state/domain.ts`:

```ts
import type { RunSnapshot } from "@/lib/contracts/rest";
import type { WorkflowRunState } from "@/lib/types";

export type WireRunSnapshot = RunSnapshot;
export type DashboardRunState = WorkflowRunState;
```

- [ ] **Step 3: Move hydrate logic**

Create `ergon-dashboard/src/lib/run-state/hydrate.ts` by moving `deserializeRunState()` and helper functions from `src/lib/runState.ts`.

Export:

```ts
export function hydrateRunSnapshot(input: unknown): WorkflowRunState {
  const data = parseRunSnapshot(input);
  // existing deserializeRunState body
}
```

Keep a compatibility alias:

```ts
export const deserializeRunState = hydrateRunSnapshot;
```

- [ ] **Step 4: Move serialize logic**

Create `ergon-dashboard/src/lib/run-state/serialize.ts` by moving `serializeRunState()` and context-event serialization from `src/lib/runState.ts`.

Export:

```ts
export function serializeRunSnapshot(run: WorkflowRunState): WireRunSnapshot {
  // existing serializeRunState body without broad unknown casts where possible
}

export const serializeRunState = serializeRunSnapshot;
```

- [ ] **Step 5: Add index exports**

Create `ergon-dashboard/src/lib/run-state/index.ts`:

```ts
export type { DashboardRunState, WireRunSnapshot } from "./domain";
export { hydrateRunSnapshot, deserializeRunState } from "./hydrate";
export { serializeRunSnapshot, serializeRunState } from "./serialize";
export { compareContextEvents } from "./contextEvents";
```

- [ ] **Step 6: Convert old file to compatibility wrapper**

Replace `ergon-dashboard/src/lib/runState.ts` with:

```ts
export {
  compareContextEvents,
  deserializeRunState,
  hydrateRunSnapshot,
  serializeRunSnapshot,
  serializeRunState,
} from "@/lib/run-state";
```

This keeps imports working while future tasks migrate call sites.

- [ ] **Step 7: Verify**

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test tests/contracts/run-state-roundtrip.contract.test.ts
pnpm -C ergon-dashboard run test:contracts
pnpm -C ergon-dashboard run typecheck
```

Expected: all pass.

## Task 3: Make Context Event Conversion A Named Boundary

**Files:**
- Create/modify: `ergon-dashboard/src/lib/run-state/contextEvents.ts`
- Modify: `ergon-dashboard/src/lib/run-state/hydrate.ts`
- Modify: `ergon-dashboard/src/lib/run-state/serialize.ts`
- Test: `ergon-dashboard/tests/contracts/context-events.contract.test.ts`

- [ ] **Step 1: Write conversion tests**

Create `ergon-dashboard/tests/contracts/context-events.contract.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import {
  contextPartToUiPayload,
  uiPayloadToContextPart,
} from "../../src/lib/run-state/contextEvents";

test("tool_call context part converts to UI payload", () => {
  const payload = contextPartToUiPayload({
    part: {
      part_kind: "tool_call",
      tool_call_id: "call-1",
      tool_name: "lean_check",
      args: { file: "proof.lean" },
    },
    token_ids: [1, 2],
    logprobs: null,
    sequence: 0,
    worker_binding_key: "react-worker",
    turn_id: "turn-1",
    started_at: "2026-03-18T12:00:00.000Z",
    completed_at: "2026-03-18T12:00:01.000Z",
    policy_version: null,
  });

  assert.deepEqual(payload, {
    event_type: "tool_call",
    tool_call_id: "call-1",
    tool_name: "lean_check",
    args: { file: "proof.lean" },
    turn_id: "turn-1",
    turn_token_ids: [1, 2],
    turn_logprobs: null,
  });
});

test("UI tool_result payload serializes to context part", () => {
  const payload = uiPayloadToContextPart(
    {
      event_type: "tool_result",
      tool_call_id: "call-1",
      tool_name: "lean_check",
      result: "ok",
      is_error: false,
    },
    {
      sequence: 3,
      workerBindingKey: "react-worker",
      startedAt: null,
      completedAt: null,
    },
  );

  assert.equal(payload.part.part_kind, "tool_result");
  assert.equal(payload.part.tool_name, "lean_check");
  assert.equal(payload.sequence, 3);
});
```

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test tests/contracts/context-events.contract.test.ts
```

Expected: FAIL because functions do not exist.

- [ ] **Step 2: Implement explicit conversion functions**

Create or update `ergon-dashboard/src/lib/run-state/contextEvents.ts`:

```ts
import type { ContextEventPayload, TokenLogprob } from "@/lib/contracts/contextEvents";

type ContextPartChunk = {
  part: Record<string, unknown>;
  token_ids?: number[] | null;
  logprobs?: TokenLogprob[] | null;
  sequence: number;
  worker_binding_key: string;
  turn_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  policy_version?: string | null;
};

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

export function contextPartToUiPayload(payload: unknown): ContextEventPayload {
  const record = asRecord(payload);
  if (typeof record.event_type === "string") {
    return payload as ContextEventPayload;
  }
  const part = asRecord(record.part);
  const tokenIds = (record.token_ids as number[] | null | undefined) ?? null;
  const logprobs = (record.logprobs as TokenLogprob[] | null | undefined) ?? null;
  const turnId = String(record.turn_id ?? "");

  switch (part.part_kind) {
    case "system_prompt":
      return { event_type: "system_prompt", text: String(part.content ?? "") };
    case "user_message":
      return { event_type: "user_message", text: String(part.content ?? ""), from_worker_key: null };
    case "assistant_text":
      return { event_type: "assistant_text", text: String(part.content ?? ""), turn_id: turnId, turn_token_ids: tokenIds, turn_logprobs: logprobs };
    case "tool_call":
      return { event_type: "tool_call", tool_call_id: String(part.tool_call_id ?? ""), tool_name: String(part.tool_name ?? ""), args: asRecord(part.args), turn_id: turnId, turn_token_ids: tokenIds, turn_logprobs: logprobs };
    case "tool_result":
      return { event_type: "tool_result", tool_call_id: String(part.tool_call_id ?? ""), tool_name: String(part.tool_name ?? ""), result: part.content ?? null, is_error: Boolean(part.is_error ?? false) };
    case "thinking":
      return { event_type: "thinking", text: String(part.content ?? ""), turn_id: turnId, turn_token_ids: tokenIds, turn_logprobs: logprobs };
    default:
      throw new Error(`Unsupported context part kind: ${String(part.part_kind)}`);
  }
}

export function uiPayloadToContextPart(
  payload: ContextEventPayload,
  meta: {
    sequence: number;
    workerBindingKey: string;
    startedAt: string | null;
    completedAt: string | null;
  },
): ContextPartChunk {
  let part: Record<string, unknown>;
  switch (payload.event_type) {
    case "system_prompt":
      part = { part_kind: "system_prompt", content: payload.text };
      break;
    case "user_message":
      part = { part_kind: "user_message", content: payload.text };
      break;
    case "assistant_text":
      part = { part_kind: "assistant_text", content: payload.text };
      break;
    case "tool_call":
      part = { part_kind: "tool_call", tool_call_id: payload.tool_call_id, tool_name: payload.tool_name, args: payload.args };
      break;
    case "tool_result":
      part = { part_kind: "tool_result", tool_call_id: payload.tool_call_id, tool_name: payload.tool_name, content: typeof payload.result === "string" ? payload.result : JSON.stringify(payload.result) ?? "", is_error: payload.is_error };
      break;
    case "thinking":
      part = { part_kind: "thinking", content: payload.text };
      break;
  }
  const turnPayload = payload as {
    turn_id?: string | null;
    turn_token_ids?: number[] | null;
    turn_logprobs?: TokenLogprob[] | null;
  };
  return {
    part,
    token_ids: turnPayload.turn_token_ids ?? null,
    logprobs: turnPayload.turn_logprobs ?? null,
    sequence: meta.sequence,
    worker_binding_key: meta.workerBindingKey,
    turn_id: turnPayload.turn_id ?? null,
    started_at: meta.startedAt,
    completed_at: meta.completedAt,
    policy_version: null,
  };
}
```

- [ ] **Step 3: Use conversion functions in hydrate and serialize**

In `hydrate.ts`, replace inline payload normalization with:

```ts
payload: contextPartToUiPayload(event.payload),
```

In `serialize.ts`, replace inline payload serialization with:

```ts
payload: uiPayloadToContextPart(event.payload, {
  sequence: event.sequence,
  workerBindingKey: event.workerBindingKey,
  startedAt: event.startedAt,
  completedAt: event.completedAt,
}) as unknown as ContextEventState["payload"],
```

- [ ] **Step 4: Verify**

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test tests/contracts/context-events.contract.test.ts
pnpm -C ergon-dashboard run test:contracts
pnpm -C ergon-dashboard run typecheck
```

Expected: all pass.

## Task 4: Centralize Harness/Backend Server Data Access

**Files:**
- Create: `ergon-dashboard/src/lib/server-data/runs.ts`
- Create: `ergon-dashboard/src/lib/server-data/cohorts.ts`
- Create: `ergon-dashboard/src/lib/server-data/experiments.ts`
- Create: `ergon-dashboard/src/lib/server-data/responses.ts`
- Modify: `ergon-dashboard/src/app/api/runs/[runId]/route.ts`
- Modify: `ergon-dashboard/src/app/api/cohorts/route.ts`
- Modify: `ergon-dashboard/src/app/api/cohorts/[cohortId]/route.ts`
- Modify: `ergon-dashboard/src/app/cohorts/[cohortId]/runs/[runId]/page.tsx`
- Modify: `ergon-dashboard/src/app/run/[runId]/page.tsx`
- Modify: `ergon-dashboard/src/app/cohorts/[cohortId]/page.tsx`
- Modify: `ergon-dashboard/src/app/experiments/[experimentId]/page.tsx`
- Test: `ergon-dashboard/tests/contracts/server-data.contract.test.ts`

- [ ] **Step 1: Write a focused experiment fallback test**

Create `ergon-dashboard/tests/contracts/server-data.contract.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { getHarnessExperiment, resetDashboardHarness } from "../../src/lib/testing/dashboardHarness";

test("harness miss for experiment is represented as null, not notFound policy", () => {
  resetDashboardHarness();
  assert.equal(getHarnessExperiment("missing-experiment"), null);
});
```

This test documents the low-level harness behavior. The route/page fallback is verified by Playwright in Task 4 Step 5.

- [ ] **Step 2: Create run data adapter**

Create `ergon-dashboard/src/lib/server-data/runs.ts`:

```ts
import { config } from "@/lib/config";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRun } from "@/lib/testing/dashboardHarness";
import type { SerializedWorkflowRunState } from "@/lib/types";

export async function loadRunSnapshot(runId: string): Promise<SerializedWorkflowRunState | null> {
  if (config.enableTestHarness) {
    const harnessRun = getHarnessRun(runId);
    if (harnessRun !== null) return harnessRun;
  }
  const response = await fetchErgonApi(`/runs/${runId}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Run API returned ${response.status}`);
  return parseRunSnapshot(await response.json());
}
```

- [ ] **Step 3: Create cohort and experiment adapters**

Create `ergon-dashboard/src/lib/server-data/experiments.ts`:

```ts
import { notFound } from "next/navigation";

import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessExperiment } from "@/lib/testing/dashboardHarness";
import type { ExperimentDetail } from "@/lib/types";

export async function loadExperimentDetail(experimentId: string): Promise<ExperimentDetail | null> {
  if (config.enableTestHarness) {
    const harnessExperiment = getHarnessExperiment(experimentId);
    if (harnessExperiment !== null) return harnessExperiment;
  }
  const response = await fetchErgonApi(`/experiments/${experimentId}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Failed to load experiment ${experimentId}: ${response.status}`);
  }
  return (await response.json()) as ExperimentDetail;
}

export async function requireExperimentDetail(experimentId: string): Promise<ExperimentDetail> {
  const detail = await loadExperimentDetail(experimentId);
  if (detail === null) notFound();
  return detail;
}
```

Create `ergon-dashboard/src/lib/server-data/cohorts.ts` with the same pattern:

```ts
import { config } from "@/lib/config";
import { parseCohortDetail, parseCohortSummaryList } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessCohort, listHarnessCohorts } from "@/lib/testing/dashboardHarness";
import type { CohortDetail, CohortSummary } from "@/lib/types";

export async function loadCohortDetail(cohortId: string): Promise<CohortDetail | null> {
  if (config.enableTestHarness) {
    const detail = getHarnessCohort(cohortId);
    if (detail !== null) return detail;
  }
  const response = await fetchErgonApi(`/cohorts/${cohortId}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Cohort API returned ${response.status}`);
  return parseCohortDetail(await response.json());
}

export async function loadCohortList(includeArchived: string | null): Promise<CohortSummary[]> {
  if (config.enableTestHarness) {
    const cohorts = listHarnessCohorts();
    if (cohorts.length > 0) return cohorts;
  }
  const path = includeArchived === null ? "/cohorts" : `/cohorts?include_archived=${includeArchived}`;
  const response = await fetchErgonApi(path);
  if (!response.ok) throw new Error(`Cohort list API returned ${response.status}`);
  return parseCohortSummaryList(await response.json());
}
```

- [ ] **Step 4: Update pages and routes to call adapters**

In `src/app/experiments/[experimentId]/page.tsx`, replace the bespoke harness block with:

```ts
const detail = await requireExperimentDetail(experimentId);
```

In run/cohort pages and API routes, call `loadRunSnapshot`, `loadCohortDetail`, and `loadCohortList`.

- [ ] **Step 5: Add browser coverage for experiment fallback**

Add to `ergon-dashboard/tests/e2e/cohort.snapshot.spec.ts` or a new `experiment.snapshot.spec.ts`:

```ts
test("experiment detail falls back to backend when dashboard harness has no fixture", async ({ page }) => {
  await page.goto(`/experiments/${FIXTURE_IDS.experimentId}`);
  await expect(page.getByRole("heading", { name: "minif2f smoke n=3" })).toBeVisible();
});
```

If this fixture is harness-owned, add a separate route-level test with mocked backend for the fallback path instead.

- [ ] **Step 6: Verify**

Run:

```bash
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run e2e
pnpm -C ergon-dashboard run typecheck
```

Expected: all pass.

## Task 5: Share Client And Server Run-State Reducers

**Files:**
- Create: `ergon-dashboard/src/lib/run-state/reducers.ts`
- Create: `ergon-dashboard/src/lib/run-state/metrics.ts`
- Modify: `ergon-dashboard/src/lib/state/store.ts`
- Modify: `ergon-dashboard/src/hooks/useRunState.ts`
- Test: `ergon-dashboard/src/hooks/useRunState.socketHydration.test.ts`
- Test: `ergon-dashboard/tests/contracts/run-state-roundtrip.contract.test.ts`

- [ ] **Step 1: Write reducer parity tests**

Extend `src/hooks/useRunState.socketHydration.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { applyTaskStatusChanged } from "@/lib/run-state/reducers";
import { createDashboardSeed, FIXTURE_IDS } from "../../tests/helpers/dashboardFixtures";
import { hydrateRunSnapshot } from "@/lib/run-state";
import { TaskStatus } from "@/lib/types";

test("task status reducer records transition history", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const state = hydrateRunSnapshot(run);
  const next = applyTaskStatusChanged(state, {
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    status: TaskStatus.COMPLETED,
    timestamp: "2026-03-18T12:01:00.000Z",
    assignedWorkerId: null,
    assignedWorkerSlug: null,
  });

  const task = next.tasks.get(FIXTURE_IDS.solveTaskId);
  assert.equal(task?.status, TaskStatus.COMPLETED);
  assert.equal(task?.history?.at(-1)?.to, TaskStatus.COMPLETED);
});
```

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test src/hooks/useRunState.socketHydration.test.ts
```

Expected: FAIL because reducer does not exist.

- [ ] **Step 2: Implement metrics helper**

Create `src/lib/run-state/metrics.ts`:

```ts
import { TaskStatus, type TaskState, type WorkflowRunState } from "@/lib/types";

export function recalculateTaskMetrics(tasks: Map<string, TaskState>): Pick<
  WorkflowRunState,
  "completedTasks" | "runningTasks" | "failedTasks" | "cancelledTasks"
> {
  let completedTasks = 0;
  let runningTasks = 0;
  let failedTasks = 0;
  let cancelledTasks = 0;

  for (const task of tasks.values()) {
    if (!task.isLeaf) continue;
    if (task.status === TaskStatus.COMPLETED) completedTasks += 1;
    if (task.status === TaskStatus.RUNNING) runningTasks += 1;
    if (task.status === TaskStatus.FAILED) failedTasks += 1;
    if (task.status === TaskStatus.CANCELLED) cancelledTasks += 1;
  }

  return { completedTasks, runningTasks, failedTasks, cancelledTasks };
}
```

- [ ] **Step 3: Implement task status reducer**

Create `src/lib/run-state/reducers.ts`:

```ts
import { inferTrigger } from "@/lib/runEvents";
import { TaskStatus, type ExecutionAttemptState, type TaskState, type WorkflowRunState } from "@/lib/types";
import { recalculateTaskMetrics } from "./metrics";

export interface TaskStatusChangedInput {
  runId: string;
  taskId: string;
  status: TaskStatus;
  timestamp: string;
  assignedWorkerId?: string | null;
  assignedWorkerSlug?: string | null;
}

function nextExecutionStatus(status: TaskStatus): TaskStatus {
  return status === TaskStatus.READY ? TaskStatus.PENDING : status;
}

export function applyTaskStatusChanged(
  state: WorkflowRunState,
  data: TaskStatusChangedInput,
): WorkflowRunState {
  const task = state.tasks.get(data.taskId);
  if (!task) return state;

  const previousStatus = task.status;
  const status = data.status;
  const trigger = previousStatus !== status ? inferTrigger(previousStatus, status) : task.lastTrigger;
  const updatedTask: TaskState = {
    ...task,
    status,
    assignedWorkerId: data.assignedWorkerId ?? task.assignedWorkerId,
    assignedWorkerSlug: data.assignedWorkerSlug ?? task.assignedWorkerSlug,
    startedAt: status === TaskStatus.RUNNING && !task.startedAt ? data.timestamp : task.startedAt,
    completedAt:
      status === TaskStatus.COMPLETED || status === TaskStatus.FAILED || status === TaskStatus.CANCELLED
        ? data.timestamp
        : task.completedAt,
    history:
      previousStatus !== status
        ? [
            ...(task.history ?? []),
            {
              from: previousStatus,
              to: status,
              trigger,
              at: data.timestamp,
              sequence: null,
              actor: data.assignedWorkerSlug ?? task.assignedWorkerSlug ?? null,
              reason: null,
            },
          ]
        : task.history,
    lastTrigger: trigger,
  };

  const tasks = new Map(state.tasks);
  tasks.set(data.taskId, updatedTask);

  const existingExecutions = state.executionsByTask.get(data.taskId) ?? [];
  const latestExecution = existingExecutions[existingExecutions.length - 1];
  let nextExecutions = existingExecutions;

  if (status === TaskStatus.RUNNING) {
    if (!latestExecution || latestExecution.status === TaskStatus.COMPLETED || latestExecution.status === TaskStatus.FAILED) {
      const createdExecution: ExecutionAttemptState = {
        id: `${data.taskId}:attempt:${existingExecutions.length + 1}`,
        taskId: data.taskId,
        attemptNumber: existingExecutions.length + 1,
        status: TaskStatus.RUNNING,
        agentId: data.assignedWorkerId ?? task.assignedWorkerId,
        agentName: data.assignedWorkerSlug ?? task.assignedWorkerSlug,
        startedAt: data.timestamp,
        completedAt: null,
        finalAssistantMessage: null,
        outputResourceIds: [],
        errorMessage: null,
        score: null,
        evaluationDetails: {},
      };
      nextExecutions = [...existingExecutions, createdExecution];
    }
  } else if (latestExecution) {
    nextExecutions = existingExecutions.map((execution, index) =>
      index === existingExecutions.length - 1
        ? {
            ...execution,
            status: nextExecutionStatus(status),
            completedAt:
              status === TaskStatus.COMPLETED || status === TaskStatus.FAILED || status === TaskStatus.CANCELLED
                ? data.timestamp
                : execution.completedAt,
            errorMessage:
              status === TaskStatus.FAILED
                ? execution.errorMessage ?? "Task execution failed"
                : execution.errorMessage,
          }
        : execution,
    );
  }

  const executionsByTask = new Map(state.executionsByTask);
  executionsByTask.set(data.taskId, nextExecutions);
  const metrics = recalculateTaskMetrics(tasks);

  return { ...state, tasks, executionsByTask, ...metrics };
}
```

- [ ] **Step 4: Use reducer in `useRunState`**

In `src/hooks/useRunState.ts`, replace the task status `setRunState` body with:

```ts
setRunState((prev) => {
  if (!prev) return prev;
  return applyTaskStatusChanged(prev, {
    runId: data.runId,
    taskId: data.taskId,
    status,
    timestamp: data.timestamp,
    assignedWorkerId: data.assignedWorkerId,
    assignedWorkerSlug: data.assignedWorkerSlug,
  });
});
```

- [ ] **Step 5: Use reducer in `DashboardStore`**

In `src/lib/state/store.ts`, replace `updateTaskStatus` internals with:

```ts
const updated = applyTaskStatusChanged(run, {
  runId,
  taskId,
  status: newStatus,
  timestamp,
  assignedWorkerId,
  assignedWorkerSlug,
});
this.runs.set(runId, updated);
```

- [ ] **Step 6: Verify**

Run:

```bash
pnpm -C ergon-dashboard exec tsx --test src/hooks/useRunState.socketHydration.test.ts
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run e2e
```

Expected: all pass.

## Task 6: Normalize Sandbox Event Ordering

**Files:**
- Modify: `ergon-dashboard/src/lib/run-state/reducers.ts`
- Modify: `ergon-dashboard/src/hooks/useRunState.ts`
- Modify: `ergon-dashboard/src/lib/state/store.ts`
- Test: `ergon-dashboard/src/hooks/useRunState.socketHydration.test.ts`

- [ ] **Step 1: Write out-of-order sandbox test**

Add:

```ts
test("sandbox command before sandbox creation is preserved", () => {
  // Build a run state without sandbox for solve task.
  // Apply command reducer first, then sandbox-created reducer.
  // Assert the sandbox contains the pending command.
});
```

Use exact fixture IDs from `tests/helpers/dashboardFixtures.ts`.

- [ ] **Step 2: Add pending command support to reducers**

Add a client/server-compatible pending command map if needed, or simplify by making `sandbox:command` trigger a snapshot reload when the sandbox is missing.

Preferred implementation:

```ts
export function applySandboxCommand(state: WorkflowRunState, taskId: string, command: SandboxCommandState): WorkflowRunState {
  const sandbox = state.sandboxesByTask.get(taskId);
  if (!sandbox) {
    return {
      ...state,
      pendingSandboxCommands: addPendingCommand(state.pendingSandboxCommands, taskId, command),
    };
  }
  // append command
}
```

If adding `pendingSandboxCommands` to `WorkflowRunState` creates too much type churn, use the snapshot-reload fallback in `useRunState` and keep server buffering as-is.

- [ ] **Step 3: Preserve backend timestamps on close**

In `useRunState.ts`, replace:

```ts
closedAt: new Date().toISOString(),
```

with:

```ts
closedAt: data.timestamp,
```

If `parseSandboxClosedSocketData` does not expose `timestamp`, update `src/lib/contracts/events.ts` and its tests.

- [ ] **Step 4: Verify**

Run:

```bash
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run e2e
```

Expected: all pass.

## Task 7: Make Route/API Parsing And Error Semantics Consistent

**Files:**
- Modify: `ergon-dashboard/src/app/api/cohorts/[cohortId]/route.ts`
- Modify: `ergon-dashboard/src/app/api/runs/[runId]/mutations/route.ts`
- Modify: `ergon-dashboard/src/app/api/training/sessions/route.ts`
- Modify: `ergon-dashboard/src/lib/serverApi.ts`
- Test: `ergon-dashboard/src/app/api/health/health.test.ts` or new API route tests

- [ ] **Step 1: Parse successful cohort detail responses**

In `src/app/api/cohorts/[cohortId]/route.ts`, successful GET should return:

```ts
return NextResponse.json(parseCohortDetail(payload), { status: response.status });
```

not raw `payload`.

- [ ] **Step 2: Choose a dependency-failure status**

Use `503` for unavailable upstream dependency across API proxy routes unless the upstream returned a concrete HTTP response.

Example:

```ts
return NextResponse.json(
  {
    detail: "Ergon API is unavailable.",
    error: error instanceof Error ? error.message : "Unknown backend fetch failure",
  },
  { status: 503 },
);
```

- [ ] **Step 3: Allow per-route backend timeout**

In `src/lib/serverApi.ts`, add:

```ts
export async function fetchErgonApi(path: string, init: RequestInit & { timeoutMs?: number } = {}) {
  const { timeoutMs = 5_000, ...requestInit } = init;
  // existing AbortController logic uses timeoutMs
}
```

Use a longer timeout in resource content proxy:

```ts
await fetchErgonApi(path, { timeoutMs: 30_000 });
```

- [ ] **Step 4: Verify**

Run:

```bash
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run typecheck
```

Expected: all pass.

## Task 8: Slim `RunWorkspacePage` After Boundaries Are Stable

**Files:**
- Create: `ergon-dashboard/src/components/run/useRunDisplayState.ts`
- Create: `ergon-dashboard/src/components/run/useRunKeyboardShortcuts.ts`
- Create: `ergon-dashboard/src/components/run/useRunPanelLayout.ts`
- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
- Test: existing Playwright `run.snapshot.spec.ts`

- [ ] **Step 1: Extract panel layout persistence**

Move localStorage layout code into:

```ts
export function useRunPanelLayout() {
  return {
    verticalLayout,
    setVerticalLayout,
    horizontalLayout,
    setHorizontalLayout,
    hasLoadedPanelLayouts,
  };
}
```

- [ ] **Step 2: Extract live/replay display state**

Create:

```ts
export function useRunDisplayState(runState: WorkflowRunState | null, mutations: DashboardGraphMutationData[]) {
  return {
    displayState,
    selectedActivity,
    selectedActivityId,
    setSelectedActivityId,
    snapshotSequence,
  };
}
```

Document the invariant:

```text
Activities and trace rows are built from full live run state.
Inspector and graph may render replay display state.
```

- [ ] **Step 3: Extract keyboard shortcuts**

Create:

```ts
export function useRunKeyboardShortcuts(options: { clearSnapshot: () => void }) {
  // Escape clears snapshot selection.
}
```

- [ ] **Step 4: Verify no UI behavior changed**

Run:

```bash
pnpm -C ergon-dashboard exec playwright test tests/e2e/run.snapshot.spec.ts
pnpm -C ergon-dashboard run typecheck
```

Expected: run workspace behavior remains identical.

## Final Verification

Run the full local verification matrix:

```bash
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard run test:contracts
pnpm -C ergon-dashboard run typecheck
pnpm -C ergon-dashboard run lint
ERGON_API_BASE_URL=http://127.0.0.1:9000 pnpm -C ergon-dashboard run e2e
ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@localhost:5433/ergon \
INNGEST_API_BASE_URL=http://localhost:8289 \
INNGEST_DEV=1 \
INNGEST_EVENT_KEY=dev \
ERGON_API_BASE_URL=http://127.0.0.1:9000 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 \
SCREENSHOT_DIR=/tmp/playwright \
PYTHONUNBUFFERED=1 \
uv run pytest tests/e2e -v --timeout=300
```

Expected:

```text
frontend unit/contract/type/lint checks pass
dashboard local e2e passes with live smoke specs skipped if env is absent
Python full-stack e2e passes
```

## Self-Review

- Spec coverage: covers test wiring, type split, context event conversion, harness/backend fallback, shared reducers, sandbox ordering, route semantics, and later component slimming.
- Placeholder scan: no `TBD` or open-ended “add tests” instructions remain; each task has target files and verification commands.
- Type consistency: canonical names are `WireRunSnapshot`, `DashboardRunState`, `hydrateRunSnapshot`, `serializeRunSnapshot`, `contextPartToUiPayload`, `uiPayloadToContextPart`, and `applyTaskStatusChanged`.

