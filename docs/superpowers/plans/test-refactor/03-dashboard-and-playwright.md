# 03 — Dashboard harness + Playwright specs + screenshots

**Status:** draft
**Scope:** every HTTP boundary and UI assertion the smoke tier depends on. Existing wiring catalogued in §1; new contract nailed down in §2–§3; Playwright specs in §5.

Cross-refs: driver calls Playwright from [`02-drivers-and-asserts.md §4`](02-drivers-and-asserts.md); CI invocation in [`04-ci-and-workflows.md`](04-ci-and-workflows.md).

---

## 1. What exists today (catalogue, before edits)

### 1.1 Backend harness

- `ergon_core/core/api/test_harness.py` — FastAPI router mounted conditionally on `ENABLE_TEST_HARNESS=1`.
- Mount gate covered by `tests/unit/test_app_mounts_harness_conditionally.py`.

### 1.2 Next.js dashboard routes (under `/api/test/*`)

- `src/app/api/test/dashboard/seed/route.ts` — seed cohort/run state for UI fixtures.
- `src/app/api/test/dashboard/reset/route.ts` — reset in-memory state.
- `src/app/api/test/dashboard/events/run-complete/route.ts` — inject run-completion event.
- `src/app/api/test/dashboard/events/thread-message/route.ts` — inject chat/turn event.
- `src/app/api/test/dashboard/events/task-evaluation/route.ts` — inject evaluation event.

### 1.3 TypeScript client

- `ergon-dashboard/tests/helpers/testHarnessClient.ts` — wraps the dashboard `/api/test/*` routes.

### 1.4 Real-LLM harness

- `tests/real_llm/fixtures/harness_client.py` — Python client for the backend harness.
- `tests/real_llm/fixtures/playwright_client.py` — subprocess wrapper.
- `tests/real_llm/fixtures/stack.py` — Docker stack orchestration.

---

## 2. Harness contract (backend, consumed by smoke)

Smoke drivers + Playwright specs agree on **one** backend harness contract. Everything else is dashboard-internal.

### 2.1 Gates

- **Mount:** `ENABLE_TEST_HARNESS=1`.
- **Per-request:** every `/api/test/*` request must carry `X-Test-Secret: ${TEST_HARNESS_SECRET}` or `?test_secret=...`. Requests without a matching secret 401.
- **Secret rotation:** CI generates a fresh per-job random value, exports it to both backend and Playwright subprocess. Local dev pins via `.env.test`.

### 2.2 Read endpoints (what Playwright calls)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/test/read/run/{run_id}/state` | Narrow DTO: `{ run_id, status, node_count, leaf_statuses: [{slug, status}], evaluation: {score, passed} \| null }` |
| GET | `/api/test/read/cohort/{cohort_key}/runs` | `[{run_id, status}]` |
| GET | `/api/test/read/run/{run_id}/resources` | `[{name, content_hash, size}]` — metadata only, no blob bytes |

Narrow DTOs — **not** raw SQL row dumps. These are contract types; the dashboard or Playwright must not depend on schema columns it doesn't need.

### 2.3 Write endpoints (optional, secret-gated)

Already-implemented Next.js routes (`events/run-complete` etc.) exist for dashboard-fixture injection. Not used by the smoke path — Playwright reads real state via §2.2.

**Decision (pinned in `00-program.md §6.4`):** keep the Next.js write routes as-is. They serve dashboard dev loop (seed state without standing up a full backend); smoke doesn't rely on them.

### 2.4 `BackendHarnessClient` (TS)

```typescript
// ergon-dashboard/tests/helpers/backendHarnessClient.ts
//
// One client, one contract. Reads only. Throws on non-2xx so Playwright
// specs don't silently assert against undefined.

export interface RunState {
  run_id: string;
  status: "completed" | "failed" | "cancelled" | "in_progress";
  node_count: number;
  leaf_statuses: { slug: string; status: string }[];
  evaluation: { score: number; passed: boolean } | null;
}

export class BackendHarnessClient {
  constructor(
    private readonly baseUrl: string,
    private readonly secret: string,
  ) {}

  async getRunState(runId: string): Promise<RunState> {
    const r = await fetch(`${this.baseUrl}/api/test/read/run/${runId}/state`, {
      headers: { "X-Test-Secret": this.secret },
    });
    if (!r.ok) throw new Error(`harness ${r.status}: ${await r.text()}`);
    return r.json();
  }

  async getCohortRuns(cohortKey: string) {
    const r = await fetch(
      `${this.baseUrl}/api/test/read/cohort/${cohortKey}/runs`,
      { headers: { "X-Test-Secret": this.secret } },
    );
    if (!r.ok) throw new Error(`harness ${r.status}`);
    return r.json() as Promise<{ run_id: string; status: string }[]>;
  }
}
```

The existing `tests/helpers/testHarnessClient.ts` targets the Next.js `/api/test/dashboard/*` routes (dashboard-side harness). The new `backendHarnessClient.ts` targets the backend `/api/test/*` router. Two clients, two contracts; smoke specs import `BackendHarnessClient` only.

---

## 3. Playwright spec template (shared across 3 envs)

`ergon-dashboard/tests/e2e/_shared/smoke.ts` — factory:

```typescript
import { test, expect, Page } from "@playwright/test";
import * as fs from "node:fs/promises";
import * as path from "node:path";

import { BackendHarnessClient } from "../../helpers/backendHarnessClient";

export interface SmokeSpecConfig {
  env: string;
  expectedSubtaskSlugs: string[];
}

export function defineSmokeSpec(cfg: SmokeSpecConfig) {
  const cohortKey = process.env.COHORT_KEY!;
  const runIds = process.env.RUN_IDS!.split(",");
  const screenshotDir = process.env.SCREENSHOT_DIR!;
  const secret = process.env.TEST_HARNESS_SECRET!;
  const apiBase = process.env.ERGON_API_BASE_URL!;

  const client = new BackendHarnessClient(apiBase, secret);

  test.describe(`${cfg.env} canonical smoke`, () => {
    for (const runId of runIds) {
      test(`run ${runId}`, async ({ page }) => {
        // 1. Backend truth via harness
        const state = await client.getRunState(runId);
        expect(state.status).toBe("completed");
        expect(state.node_count).toBe(10);           // root + 9
        expect(state.leaf_statuses.length).toBe(9);
        expect(new Set(state.leaf_statuses.map(l => l.slug)))
          .toEqual(new Set(cfg.expectedSubtaskSlugs));
        expect(state.evaluation?.score).toBe(1.0);

        // 2. Run page
        await page.goto(`/run/${runId}`);
        await expect(page.getByTestId("run-status")).toHaveText(/completed/i);
        const nodes = page.getByTestId("task-node");
        await expect(nodes).toHaveCount(9);
        for (const slug of cfg.expectedSubtaskSlugs) {
          await expect(page.getByTestId(`task-node-${slug}`)).toBeVisible();
          await expect(page.getByTestId(`task-node-${slug}`))
            .toHaveAttribute("data-status", "completed");
        }
        await screenshot(page, path.join(screenshotDir, cfg.env, `${runId}-run-full.png`),
                         { fullPage: true });
        await screenshot(page.getByTestId("graph-canvas"),
                         path.join(screenshotDir, cfg.env, `${runId}-graph.png`));
      });
    }

    test("cohort index lists all runs", async ({ page }) => {
      await page.goto(`/cohort/${cohortKey}`);
      await expect(page.getByTestId("cohort-run-row"))
        .toHaveCount(runIds.length);
      await screenshot(page, path.join(screenshotDir, cfg.env, `cohort-${cohortKey}.png`),
                       { fullPage: true });
    });
  });
}

async function screenshot(target: Page | ReturnType<Page["getByTestId"]>, out: string, opts?: any) {
  await fs.mkdir(path.dirname(out), { recursive: true });
  if ("screenshot" in target) {
    await (target as any).screenshot({ path: out, ...opts });
  }
}
```

Per-env specs are 3-liners:

```typescript
// ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
import { defineSmokeSpec } from "./_shared/smoke";
import { EXPECTED_SUBTASK_SLUGS } from "./_shared/expected";

defineSmokeSpec({ env: "researchrubrics", expectedSubtaskSlugs: EXPECTED_SUBTASK_SLUGS });
```

```typescript
// ergon-dashboard/tests/e2e/_shared/expected.ts
export const EXPECTED_SUBTASK_SLUGS = [
  "d_root", "d_left", "d_right", "d_join",
  "l_1", "l_2", "l_3",
  "s_a", "s_b",
];
```

(Same tuple as Python's `EXPECTED_SUBTASK_SLUGS` — duplicated because cross-language share is more work than it's worth; both exports live in small files and diverge loudly.)

---

## 4. Per-env Playwright deltas

Minimal — content checks happen on the Python side via artifact reads. Playwright asserts the UI contract only. Two additions over a naïve per-run loop:

### 4.1 Cohort label on the cohort index

```typescript
await expect(page.getByTestId("cohort-env-label"))
  .toHaveText(new RegExp(cfg.env, "i"));
```

### 4.2 Mixed happy/sad cohort dispatch (researchrubrics only)

The Python driver passes `cohort: [{ run_id, kind }, …]` via env var (JSON-encoded). The shared factory iterates it and branches on `kind`. Happy-path assertions stay as in §3; sad-path assertions (for researchrubrics slot 3) run the block specified in [`02-drivers-and-asserts.md §10.2`](02-drivers-and-asserts.md):

```typescript
// inside defineSmokeSpec, per-run loop:
for (const { run_id, kind } of cohort) {
  test(`run ${run_id} (${kind})`, async ({ page }) => {
    if (kind === "happy") {
      // happy-path assertions (§3)
    } else {
      // sad-run: l_2 FAILED, l_3 BLOCKED/CANCELLED, rest COMPLETED (§10.2 of 02-...)
    }
  });
}
```

MiniF2F and SWE-bench cohorts pass 3 × `{ run_id, kind: "happy" }`, so the sad branch is dead code for those envs.

### 4.3 Env-specific content (when needed)

If an env needs a richer UI check later (e.g. MiniF2F theorem preview), extend `SmokeSpecConfig` with an optional `extraRunAssertions(page, runId): Promise<void>` and call it from the happy-path block.

---

## 5. Screenshots captured (per leg)

Per matrix leg, after all 3 cohort runs:

| File | Contents |
|---|---|
| `<env>/<run_id>-run-full.png` × 3 | Full `/run/{id}` page |
| `<env>/<run_id>-graph.png` × 3 | `graph-canvas` element only (zoomed on DAG) |
| `<env>/cohort-<cohort_key>.png` | Cohort index with all 3 runs listed |

7 PNGs per leg × 3 legs = 21 per PR. File naming is stable so the `gh pr comment` can reference them by path.

---

## 6. Dashboard `data-testid` contract (frontend-side work)

The spec assumes these test IDs exist:

| testid | Element |
|---|---|
| `run-status` | Text showing run status on `/run/{id}` |
| `task-node` (list) | Each DAG node in the graph canvas |
| `task-node-{slug}` | A specific node by task slug |
| `graph-canvas` | The graph container element |
| `cohort-run-row` | Each row on `/cohort/{key}` listing one run |
| `cohort-env-label` | Env display on cohort index |

If today's dashboard uses different attributes (classes, aria-labels), add `data-testid` attributes as part of this PR. `data-testid` is the contract; the Playwright spec does not fall back to text-matching.

---

## 7. Harness unit tests (kept, aligned)

| Test | What it asserts | Lives |
|---|---|---|
| `test_app_mounts_harness_conditionally.py` | `/api/test/*` only mounts if `ENABLE_TEST_HARNESS=1` | `tests/unit/` |
| `test_test_harness.py` (existing) | Secret-gate 401 behaviour | `tests/unit/` |
| `test_smoke_harness.py` (existing) | Harness round-trip against real Postgres | `tests/integration/smokes/` |

These stay and are aligned to the catalogued read DTOs in §2.2 — if a DTO changes, these tests change with it.
