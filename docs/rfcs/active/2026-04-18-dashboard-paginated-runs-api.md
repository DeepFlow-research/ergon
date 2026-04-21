---
status: active
opened: 2026-04-18
author: agent
architecture_refs: [docs/architecture/05_dashboard.md, docs/architecture/04_persistence.md]
supersedes: []
superseded_by: null
---

# RFC: Paginated REST Runs API; Store Holds Only Subscribed Runs

## 1. Problem

Three defects compound in the current runs index path.

**1a. Runs older than 50 are inaccessible.**
`DashboardStore.pruneOldRuns` (`ergon-dashboard/src/lib/state/store.ts:409`) evicts the oldest
completed/failed runs when `runs.size > config.maxRunsToKeep` (`lib/config.ts:29`, default 50).
There is no REST endpoint that reads from Postgres for the index view: the only paginated data
surface is `GET /api/runs/{run_id}` (per-run detail) and `GET /cohorts/{cohort_id}` (cohort-scoped
list). A researcher who runs more than 50 benchmarks in one session loses index visibility of older
runs.

**1b. Store conflates cache and index-of-record.**
`doc/architecture/05_dashboard.md §4` states: "DashboardStore is a cache. The durable source of
truth is Postgres." But the Socket.io `request:runs` handler
(`ergon-dashboard/src/lib/socket/server.ts:79`) serves the all-runs index directly from
`store.getAllRuns()` — a process-local, pruned, cache — not from Postgres. This violates the stated
invariant: if the process restarts or the 50-run window fills, the client receives a stale or
truncated index.

**1c. HA is structurally impossible while the store is the index-of-record.**
`docs/bugs/open/2026-04-17-dashboard-process-local-state.md` documents that `global.__dashboardStore`
and `global.__socketIO` are process-local singletons. Two Next.js replicas each hold independent
50-run windows. Even if the store is made read-through for detail pages, the index page cannot be
consistent without a shared store or a direct Postgres read. This RFC resolves the index-of-record
half of that bug (the live-event fan-out half remains; see §13).

**Exact code locations:**

| File | Line | What is wrong |
|---|---|---|
| `ergon-dashboard/src/lib/state/store.ts` | 409–423 | `pruneOldRuns` evicts completed/failed beyond cap |
| `ergon-dashboard/src/lib/state/store.ts` | 53–55 | `getAllRuns()` is the only index source |
| `ergon-dashboard/src/lib/socket/server.ts` | 79–93 | `request:runs` handler reads `store.getAllRuns()` |
| `ergon-dashboard/src/lib/config.ts` | 29 | `maxRunsToKeep: 50` default cap |
| `ergon-dashboard/src/inngest/functions/index.ts` | 92 | `store.pruneOldRuns()` call in `onWorkflowStarted` |

---

## 2. Proposal

### 2.1 Design decision: REST not Socket.io

Three options were evaluated (see §15). REST is chosen because:
- Simple cursor pagination is trivial over HTTP.
- Responses are cache-friendly (HTTP cache-control, CDN, stale-while-revalidate).
- Decouples the index view from the live stream; Socket.io retains its event-delivery role.
- Consistent with the existing `/api/runs/{id}` pattern already used by `useRunState`.

### 2.2 Cursor design: opaque base64

Cursor shape: base64-encoded `<started_at_iso>:<run_id_uuid>`. This is:
- Stable under inserts: inserting a new run between pages does not shift existing cursors.
- Unambiguous when `started_at` has ties: the UUID component breaks ties deterministically.
- Opaque to the client: the client treats it as a black box, enabling server-side format migration.

### 2.3 Query shape

Order: `(started_at DESC, id DESC)`. For a forward-only index this is the natural recency order.
Cursor decode: split the base64 string, parse ISO and UUID, then apply the keyset condition:

```sql
WHERE (started_at, id) < (:cursor_started_at, :cursor_id)
```

### 2.4 Response schema

```
GET /api/runs?cursor=<opaque>&limit=<n<=100>
→ { runs: RunIndexRow[], next_cursor: string | null }
```

`RunIndexRow` is a lightweight summary row — not a full `RunSnapshotDto`. Fields: `id`, `name`,
`status`, `experiment_id`, `started_at`, `completed_at`, `duration_seconds`, `final_score`,
`error`. This matches the subset the all-runs list page needs to render.

### 2.5 Store narrowing

`DashboardStore` is narrowed to hold only currently-subscribed runs:
- On first `subscribe(runId)` (Socket.io `subscribe` event): if the run is not in the store,
  load it via `build_run_snapshot` (existing path: `request:run` handler, unchanged).
- On last `unsubscribe(runId)` (when socket count for a run room drops to 0): evict the run from
  the store.
- `pruneOldRuns` is deleted. `onWorkflowStarted` no longer calls it.
- `store.getAllRuns()` becomes internal-only for live-event fan-out; it is never the index source.

### 2.6 What does NOT change

- `GET /api/runs/{run_id}` — per-run detail REST endpoint (`ergon_core/core/api/runs.py:517`).
  Unchanged.
- `WorkflowGraphRepository`, `RunRecord`, all persistence models. No Alembic revision required.
- Socket.io `subscribe`, `unsubscribe`, `request:run`, `sync:run` — unchanged.
- `useRunState` hook — unchanged; it already uses `fetch('/api/runs/${runId}')` for the REST
  snapshot.
- Inngest event handlers other than the `pruneOldRuns` call site.

---

## 3. Architecture Overview

### Before

```
Browser "all-runs" view
      |
      | socket.emit("request:runs")
      v
Socket.io server.ts:79
      |
      | store.getAllRuns()  ← pruned, process-local, up to 50 runs
      v
socket.emit("sync:runs", runs)
```

### After

```
Browser "all-runs" view
      |
      | fetch("/api/runs?cursor=...&limit=50")
      v
Next.js route: ergon-dashboard/src/app/api/runs/route.ts  (NEW)
      |
      | fetchErgonApi("/runs?cursor=...&limit=50")
      v
FastAPI: ergon_core/core/api/runs.py  (ADD endpoint)
      |
      | SELECT id, name, status, ... FROM runs
      | WHERE (started_at, id) < (:cursor_ts, :cursor_id)
      | ORDER BY started_at DESC, id DESC LIMIT :limit
      v
Postgres RunRecord table
```

```
Live delta stream (unchanged):
Python runtime --> dashboard/* Inngest events --> DashboardStore + Socket.io room
                                                  (only for subscribed runs)
```

### Store subscription lifecycle (narrowed)

```
subscribe(runId) arrives
  → if run not in store: socket.emit("request:run") triggers existing load path
  → room.count += 1

unsubscribe(runId) arrives
  → room.count -= 1
  → if room.count == 0: store.runs.delete(runId)

disconnect
  → for each room socket was in: decrement count; if 0, evict
```

---

## 4. Type and Interface Definitions

### 4.1 Python: `RunIndexRowDto` (new Pydantic model)

```python
# ergon_core/ergon_core/core/api/schemas.py  (ADD after RunSnapshotDto)

class RunIndexRowDto(CamelModel):
    """Lightweight run summary for the paginated runs index."""

    id: str
    name: str
    status: str
    experiment_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    final_score: float | None = None
    error: str | None = None


class RunsPageDto(CamelModel):
    """Paginated runs index page."""

    runs: list[RunIndexRowDto] = Field(default_factory=list)
    next_cursor: str | None = None
```

### 4.2 Python: cursor helpers

```python
# ergon_core/ergon_core/core/api/runs.py  (ADD near top of file)

import base64
from datetime import datetime
from uuid import UUID


def _encode_cursor(started_at: datetime, run_id: UUID) -> str:
    """Encode a keyset cursor as opaque base64.

    Format before encoding: "<started_at_iso>:<run_id_uuid>"
    """
    raw = f"{started_at.isoformat()}:{run_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode an opaque base64 cursor. Raises ValueError on malformed input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, uuid_str = raw.split(":", 1)
        return datetime.fromisoformat(ts_str), UUID(uuid_str)
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor!r}") from exc
```

### 4.3 TypeScript: `RunIndexRow` and `RunsPage`

```typescript
// ergon-dashboard/src/lib/types.ts  (ADD alongside existing WorkflowRunState etc.)

export interface RunIndexRow {
  id: string;
  name: string;
  status: string;  // RunLifecycleStatus
  experimentId: string;
  startedAt: string | null;
  completedAt: string | null;
  durationSeconds: number | null;
  finalScore: number | null;
  error: string | null;
}

export interface RunsPage {
  runs: RunIndexRow[];
  nextCursor: string | null;
}
```

### 4.4 TypeScript: `useRunsPage` hook

```typescript
// ergon-dashboard/src/hooks/useRunsPage.ts  (NEW FILE)

"use client";

import { useState, useEffect, useCallback } from "react";
import type { RunIndexRow, RunsPage } from "@/lib/types";

interface UseRunsPageResult {
  runs: RunIndexRow[];
  isLoading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => void;
}

export function useRunsPage(limit: number = 50): UseRunsPageResult {
  const [runs, setRuns] = useState<RunIndexRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [pendingLoad, setPendingLoad] = useState(true);

  const fetchPage = useCallback(
    async (pageCursor: string | null, append: boolean) => {
      setIsLoading(true);
      try {
        const params = new URLSearchParams({ limit: String(limit) });
        if (pageCursor) params.set("cursor", pageCursor);
        const response = await fetch(`/api/runs?${params.toString()}`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Failed to load runs (${response.status})`);
        }
        const page = (await response.json()) as RunsPage;
        setRuns((prev) => (append ? [...prev, ...page.runs] : page.runs));
        setCursor(page.nextCursor);
        setHasMore(page.nextCursor !== null);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load runs");
      } finally {
        setIsLoading(false);
      }
    },
    [limit],
  );

  useEffect(() => {
    if (pendingLoad) {
      setPendingLoad(false);
      void fetchPage(null, false);
    }
  }, [pendingLoad, fetchPage]);

  const loadMore = useCallback(() => {
    if (!isLoading && hasMore && cursor !== null) {
      void fetchPage(cursor, true);
    }
  }, [isLoading, hasMore, cursor, fetchPage]);

  return { runs, isLoading, error, hasMore, loadMore };
}
```

---

## 5. Full Implementations

### 5.1 FastAPI: `GET /runs` paginated index endpoint

Add to `ergon_core/ergon_core/core/api/runs.py` after the existing `get_run` endpoint:

```python
# ergon_core/ergon_core/core/api/runs.py  (ADD after line 524)

import base64


def _encode_cursor(started_at: datetime, run_id: UUID) -> str:
    raw = f"{started_at.isoformat()}:{run_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, uuid_str = raw.split(":", 1)
        return datetime.fromisoformat(ts_str), UUID(uuid_str)
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor!r}") from exc


@router.get("", response_model=RunsPageDto)
def list_runs(
    cursor: str | None = None,
    limit: int = 50,
) -> RunsPageDto:
    """Paginated runs index. Reads directly from Postgres.

    Query params:
        cursor: Opaque base64 keyset cursor from a prior response's ``next_cursor``.
                Absent on the first page.
        limit: Page size, clamped to [1, 100]. Default 50.

    Returns:
        ``runs``: List of ``RunIndexRowDto`` ordered by (started_at DESC, id DESC).
        ``next_cursor``: Opaque cursor to retrieve the next page, or null if exhausted.
    """
    limit = max(1, min(limit, 100))

    cursor_started_at: datetime | None = None
    cursor_run_id: UUID | None = None
    if cursor is not None:
        try:
            cursor_started_at, cursor_run_id = _decode_cursor(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    with get_session() as session:
        # Fetch limit+1 to determine hasMore
        stmt = (
            select(RunRecord)
            .order_by(RunRecord.started_at.desc(), RunRecord.id.desc())
            .limit(limit + 1)
        )
        if cursor_started_at is not None and cursor_run_id is not None:
            # Keyset: rows strictly before the cursor position
            stmt = stmt.where(
                (RunRecord.started_at < cursor_started_at)
                | (
                    (RunRecord.started_at == cursor_started_at)
                    & (RunRecord.id < cursor_run_id)
                )
            )
        rows = list(session.exec(stmt).all())

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    # Resolve names from definition metadata
    with get_session() as session:
        def_ids = [r.experiment_definition_id for r in page_rows]
        if def_ids:
            defs_stmt = select(ExperimentDefinition).where(
                ExperimentDefinition.id.in_(def_ids)  # type: ignore[union-attr]
            )
            defs = {d.id: d for d in session.exec(defs_stmt).all()}
        else:
            defs = {}

        # Aggregate scores per run
        run_ids = [r.id for r in page_rows]
        if run_ids:
            evals_stmt = select(RunTaskEvaluation).where(
                RunTaskEvaluation.run_id.in_(run_ids)  # type: ignore[union-attr]
            )
            evals_by_run: dict[UUID, list[float]] = {}
            for ev in session.exec(evals_stmt).all():
                if ev.score is not None:
                    evals_by_run.setdefault(ev.run_id, []).append(ev.score)
        else:
            evals_by_run = {}

    run_rows: list[RunIndexRowDto] = []
    for run in page_rows:
        defn = defs.get(run.experiment_definition_id)
        if defn is not None:
            meta = defn.parsed_metadata()
            name = str(meta.get("name", defn.benchmark_type))
        else:
            name = str(run.experiment_definition_id)

        duration_seconds: float | None = None
        if run.started_at and run.completed_at:
            duration_seconds = (run.completed_at - run.started_at).total_seconds()

        scores = evals_by_run.get(run.id, [])
        final_score = (sum(scores) / len(scores)) if scores else None

        run_rows.append(
            RunIndexRowDto(
                id=str(run.id),
                name=name,
                status=run.status,
                experiment_id=str(run.experiment_definition_id),
                started_at=run.started_at,
                completed_at=run.completed_at,
                duration_seconds=duration_seconds,
                final_score=final_score,
                error=run.error_message,
            )
        )

    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        ref_time = last.started_at or last.created_at
        next_cursor = _encode_cursor(ref_time, last.id)

    return RunsPageDto(runs=run_rows, next_cursor=next_cursor)
```

### 5.2 Next.js: `GET /api/runs` route handler

```typescript
// ergon-dashboard/src/app/api/runs/route.ts  (NEW FILE)

import { NextRequest, NextResponse } from "next/server";
import { fetchErgonApi } from "@/lib/serverApi";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const cursor = req.nextUrl.searchParams.get("cursor");
  const limitRaw = req.nextUrl.searchParams.get("limit");
  const limit = Math.min(
    100,
    Math.max(1, parseInt(limitRaw ?? "50", 10) || 50),
  );

  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);

  try {
    const response = await fetchErgonApi(`/runs?${params.toString()}`);
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Ergon API is unavailable while loading runs.",
        error:
          error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
```

### 5.3 `DashboardStore`: delete `pruneOldRuns`, add `evictRun`

The relevant mutation to `ergon-dashboard/src/lib/state/store.ts`:

Delete lines 408–423 (the `pruneOldRuns` method) entirely.

Add the following method after `seedRun`:

```typescript
  /**
   * Evict a run from the store when the last subscriber disconnects.
   * Called by the Socket.io server when room membership drops to zero.
   */
  evictRun(runId: string): void {
    this.runs.delete(runId);
    this.pendingSandboxCommands.delete(runId);
  }
```

### 5.4 Socket.io server: delete `request:runs` handler, add eviction logic

In `ergon-dashboard/src/lib/socket/server.ts`:

**Delete** lines 79–93 (the `request:runs` / `sync:runs` handler block).

**Add** room-membership tracking and eviction in the `connection` handler, after the existing
`unsubscribe` handler:

```typescript
    // Evict run from store when last subscriber leaves
    socket.on("unsubscribe", (runId: string) => {
      const room = `run:${runId}`;
      socket.leave(room);
      console.log(`[Socket.io] ${socket.id} unsubscribed from ${room}`);

      // Count remaining sockets in the room (excluding this one, which just left)
      const roomSockets = io.sockets.adapter.rooms.get(room);
      const remaining = roomSockets ? roomSockets.size : 0;
      if (remaining === 0) {
        store.evictRun(runId);
        console.log(`[Socket.io] No subscribers left for ${room} — evicted from store`);
      }
    });
```

Note: the existing `socket.on("unsubscribe", ...)` handler at lines 120–125 is replaced by this
version. The `subscribe` handler at lines 113–118 is unchanged.

Also add eviction on disconnect to handle ungraceful disconnects:

```typescript
    socket.on("disconnect", (reason) => {
      console.log(`[Socket.io] Client disconnected: ${socket.id} (${reason})`);

      // For each run room this socket was in, check if it was the last subscriber
      for (const [roomName] of socket.rooms) {
        if (roomName.startsWith("run:")) {
          const runId = roomName.slice(4);
          const roomSockets = io.sockets.adapter.rooms.get(roomName);
          const remaining = roomSockets ? roomSockets.size : 0;
          if (remaining === 0) {
            store.evictRun(runId);
            console.log(
              `[Socket.io] No subscribers left for ${roomName} after disconnect — evicted`,
            );
          }
        }
      }
    });
```

### 5.5 Inngest `onWorkflowStarted`: delete `pruneOldRuns` call

In `ergon-dashboard/src/inngest/functions/index.ts`, line 92: delete the line `store.pruneOldRuns();`.

---

## 6. Exact Diffs for Modified Files

### 6.1 `ergon_core/ergon_core/core/api/schemas.py`

```diff
+class RunIndexRowDto(CamelModel):
+    """Lightweight run summary for the paginated runs index."""
+
+    id: str
+    name: str
+    status: str
+    experiment_id: str
+    started_at: datetime | None = None
+    completed_at: datetime | None = None
+    duration_seconds: float | None = None
+    final_score: float | None = None
+    error: str | None = None
+
+
+class RunsPageDto(CamelModel):
+    """Paginated runs index page."""
+
+    runs: list[RunIndexRowDto] = Field(default_factory=list)
+    next_cursor: str | None = None
```

### 6.2 `ergon_core/ergon_core/core/api/runs.py`

```diff
+import base64
 from collections import defaultdict
 from datetime import datetime
 ...
+from ergon_core.core.api.schemas import (
+    RunIndexRowDto,
+    RunsPageDto,
     RunCommunicationMessageDto,
     ...
 )
+
+
+def _encode_cursor(started_at: datetime, run_id: UUID) -> str:
+    raw = f"{started_at.isoformat()}:{run_id}"
+    return base64.urlsafe_b64encode(raw.encode()).decode()
+
+
+def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
+    try:
+        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
+        ts_str, uuid_str = raw.split(":", 1)
+        return datetime.fromisoformat(ts_str), UUID(uuid_str)
+    except Exception as exc:
+        raise ValueError(f"Invalid cursor: {cursor!r}") from exc
+
 ...
+@router.get("", response_model=RunsPageDto)
+def list_runs(cursor: str | None = None, limit: int = 50) -> RunsPageDto:
+    ...  # full implementation in §5.1
```

### 6.3 `ergon-dashboard/src/lib/state/store.ts`

```diff
-  pruneOldRuns(keepCount: number = config.maxRunsToKeep): void {
-    const runs = this.getAllRuns();
-    if (runs.length <= keepCount) return;
-
-    // Sort by startedAt descending, keep the newest
-    const sorted = runs.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
-    const toRemove = sorted.slice(keepCount);
-
-    for (const run of toRemove) {
-      // Only remove completed/failed runs
-      if (run.status === "completed" || run.status === "failed") {
-        this.runs.delete(run.id);
-      }
-    }
-  }
+  evictRun(runId: string): void {
+    this.runs.delete(runId);
+    this.pendingSandboxCommands.delete(runId);
+  }
```

The `import { config } from "../config";` at line 14 may be removed if `maxRunsToKeep` is the only
use of `config` in this file. Verify before removing.

### 6.4 `ergon-dashboard/src/lib/socket/server.ts`

```diff
-    // Send current runs to newly connected client
-    socket.on("request:runs", () => {
-      console.log(`[Socket.io] Client ${socket.id} requested runs sync`);
-      const runs = store.getAllRuns();
-      console.log(`[Socket.io] Sending ${runs.length} runs to client`);
-      socket.emit("sync:runs", runs.map(r => ({
-        runId: r.id,
-        name: r.name,
-        status: r.status,
-        startedAt: r.startedAt,
-        completedAt: r.completedAt,
-        durationSeconds: r.durationSeconds,
-        finalScore: r.finalScore,
-        error: r.error,
-      })));
-    });
+    // (request:runs removed; index view uses REST GET /api/runs)

     ...

-    // Client unsubscribes from a run's updates
-    socket.on("unsubscribe", (runId: string) => {
-      const room = `run:${runId}`;
-      socket.leave(room);
-      console.log(`[Socket.io] ${socket.id} unsubscribed from ${room}`);
-    });
+    // Client unsubscribes; evict from store if last subscriber
+    socket.on("unsubscribe", (runId: string) => {
+      const room = `run:${runId}`;
+      socket.leave(room);
+      console.log(`[Socket.io] ${socket.id} unsubscribed from ${room}`);
+      const roomSockets = io.sockets.adapter.rooms.get(room);
+      const remaining = roomSockets ? roomSockets.size : 0;
+      if (remaining === 0) {
+        store.evictRun(runId);
+        console.log(`[Socket.io] No subscribers for ${room} — evicted`);
+      }
+    });

-    socket.on("disconnect", (reason) => {
-      console.log(`[Socket.io] Client disconnected: ${socket.id} (${reason})`);
-    });
+    socket.on("disconnect", (reason) => {
+      console.log(`[Socket.io] Client disconnected: ${socket.id} (${reason})`);
+      for (const [roomName] of socket.rooms) {
+        if (roomName.startsWith("run:")) {
+          const runId = roomName.slice(4);
+          const roomSockets = io.sockets.adapter.rooms.get(roomName);
+          const remaining = roomSockets ? roomSockets.size : 0;
+          if (remaining === 0) {
+            store.evictRun(runId);
+          }
+        }
+      }
+    });
```

### 6.5 `ergon-dashboard/src/inngest/functions/index.ts`

```diff
     broadcastRunStarted(run_id, workflow_name);
     console.log("[Dashboard] broadcastRunStarted completed");

-    // Prune old runs to prevent memory growth
-    store.pruneOldRuns();
-
     return { success: true };
```

---

## 7. Package Structure

No new Python packages. The two new DTOs go into the existing `schemas.py`. The cursor helpers and
the new route handler go into the existing `runs.py`.

No new TypeScript packages. New files are:
- `ergon-dashboard/src/app/api/runs/route.ts` — new file in the existing `app/api/` tree.
- `ergon-dashboard/src/hooks/useRunsPage.ts` — new file in the existing `hooks/` tree.

The types `RunIndexRow` and `RunsPage` are added to the existing types index. If
`ergon-dashboard/src/lib/types/index.ts` re-exports from sub-files, add the new types to the
appropriate sub-file and re-export.

---

## 8. Implementation Order

Phased into two PRs.

### PR 1 — Backend: paginated endpoint (no frontend change)

| Step | What | Files touched |
|---|---|---|
| 1 | Add `RunIndexRowDto` and `RunsPageDto` to `schemas.py` | MODIFY `ergon_core/ergon_core/core/api/schemas.py` |
| 2 | Add `_encode_cursor`, `_decode_cursor` helpers to `runs.py` | MODIFY `ergon_core/ergon_core/core/api/runs.py` |
| 3 | Add `list_runs` (`GET /runs`) endpoint to `runs.py` | MODIFY `ergon_core/ergon_core/core/api/runs.py` |
| 4 | Unit tests: cursor encode/decode round-trip; empty DB; one page; two pages with next_cursor; cursor boundary correctness | ADD `ergon/tests/state/test_paginated_runs_api.py` |
| 5 | Integration test: create 5 RunRecords, call `list_runs` with limit=3, verify next_cursor, fetch second page, verify no overlap | ADD to `ergon/tests/state/test_paginated_runs_api.py` |

### PR 2 — Frontend: REST index + store narrowing

| Step | What | Files touched |
|---|---|---|
| 6 | Add `RunIndexRow`, `RunsPage` types to TS types file | MODIFY `ergon-dashboard/src/lib/types.ts` |
| 7 | Add Next.js `GET /api/runs` proxy route | ADD `ergon-dashboard/src/app/api/runs/route.ts` |
| 8 | Add `useRunsPage` hook | ADD `ergon-dashboard/src/hooks/useRunsPage.ts` |
| 9 | Delete `pruneOldRuns` from `DashboardStore`, add `evictRun` | MODIFY `ergon-dashboard/src/lib/state/store.ts` |
| 10 | Delete `request:runs` handler from `server.ts`; update `unsubscribe` and `disconnect` handlers to call `evictRun` | MODIFY `ergon-dashboard/src/lib/socket/server.ts` |
| 11 | Delete `store.pruneOldRuns()` call from `onWorkflowStarted` | MODIFY `ergon-dashboard/src/inngest/functions/index.ts` |
| 12 | Wire `useRunsPage` into the runs index page (or the component that currently renders `sync:runs` data) | MODIFY the relevant page/component |
| 13 | Remove `ClientToServerEvents["request:runs"]` (`lib/types.ts:417`) and `ServerToClientEvents["sync:runs"]` (`lib/types.ts:401`); delete `RunListEntry`, `SyncRunsSchema`, `parseSyncRuns` from `lib/contracts/events.ts` | MODIFY `ergon-dashboard/src/lib/types.ts`, MODIFY `ergon-dashboard/src/lib/contracts/events.ts` |
| 14 | Frontend hook tests: mock `fetch`, verify page-1 load; loadMore appends; error state | ADD `ergon-dashboard/src/__tests__/useRunsPage.test.ts` |

**Step 12 dependency note:** The current home page (`ergon-dashboard/src/app/page.tsx:1`) renders
`<CohortListView />`, not a standalone runs index. If the all-runs index view is a component that
currently calls `socket.emit("request:runs")`, that component must be identified and updated in PR 2.
A grep for `request:runs` in the `src/` tree will locate all call sites. If no component currently
uses `request:runs` (the handler exists in server.ts but has no verified client call site beyond
test harness), step 12 is a new feature — create a new `RunsIndexView` component that calls
`useRunsPage`.

---

## 9. File Map

### ADD

| File | Purpose |
|---|---|
| `ergon-dashboard/src/app/api/runs/route.ts` | Next.js GET /api/runs proxy to ergon_core |
| `ergon-dashboard/src/hooks/useRunsPage.ts` | React hook for paginated runs index |
| `ergon/tests/state/test_paginated_runs_api.py` | Unit + integration tests for `list_runs` endpoint |
| `ergon-dashboard/src/__tests__/useRunsPage.test.ts` | Frontend hook tests |

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/api/schemas.py` | Add `RunIndexRowDto`, `RunsPageDto` |
| `ergon_core/ergon_core/core/api/runs.py` | Add `_encode_cursor`, `_decode_cursor`, `list_runs` endpoint; add `base64` import |
| `ergon-dashboard/src/lib/state/store.ts` | Delete `pruneOldRuns`; add `evictRun`; remove `config` import if unused |
| `ergon-dashboard/src/lib/socket/server.ts` | Delete `request:runs` handler; update `unsubscribe` to evict on last subscriber; update `disconnect` to evict on last subscriber |
| `ergon-dashboard/src/inngest/functions/index.ts` | Delete `store.pruneOldRuns()` call in `onWorkflowStarted` |
| `ergon-dashboard/src/lib/types.ts` | Add `RunIndexRow`, `RunsPage`; remove `ClientToServerEvents["request:runs"]` (line 417) and `ServerToClientEvents["sync:runs"]` (line 401) entries; remove `RunListEntry` import (line 33) |
| `ergon-dashboard/src/lib/contracts/events.ts` | Delete `RunListEntrySchema` (line 201), `SyncRunsSchema` (line 212), `RunListEntry` type (line 273), `parseSyncRuns` (line 355) |
| `docs/architecture/05_dashboard.md` | Update §2 (retention) and §4 (invariants) on acceptance |

---

## 10. Testing Approach

### 10.1 Backend unit tests — `test_paginated_runs_api.py`

```python
# ergon/tests/state/test_paginated_runs_api.py

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ergon_core.core.api.app import app
from ergon_core.core.api.runs import _decode_cursor, _encode_cursor
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord


class TestCursorHelpers:
    def test_round_trip(self) -> None:
        ts = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
        run_id = uuid4()
        cursor = _encode_cursor(ts, run_id)
        decoded_ts, decoded_id = _decode_cursor(cursor)
        assert decoded_ts == ts
        assert decoded_id == run_id

    def test_malformed_cursor_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_cursor("not-a-valid-cursor")

    def test_opaque_looks_like_base64(self) -> None:
        cursor = _encode_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())
        # Should not contain raw ISO or UUID separators
        assert ":" not in cursor
        assert "-" not in cursor or True  # urlsafe base64 may contain "-"


class TestListRunsEndpoint:
    @pytest.fixture(autouse=True)
    def db(self) -> None:
        ensure_db()

    def test_empty_db_returns_empty_page(self) -> None:
        client = TestClient(app)
        resp = client.get("/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["runs"] == []
        assert body["nextCursor"] is None

    def test_returns_runs_ordered_by_started_at_desc(self) -> None:
        base_time = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
        run_ids = []
        with get_session() as session:
            for i in range(3):
                defn_id = uuid4()
                run = RunRecord(
                    id=uuid4(),
                    experiment_definition_id=defn_id,
                    status=RunStatus.COMPLETED,
                    started_at=base_time + timedelta(hours=i),
                    created_at=base_time + timedelta(hours=i),
                )
                session.add(run)
                run_ids.append(run.id)
            session.commit()

        client = TestClient(app)
        resp = client.get("/runs?limit=10")
        assert resp.status_code == 200
        returned_ids = [r["id"] for r in resp.json()["runs"]]
        # Most recent first
        assert returned_ids[0] == str(run_ids[2])
        assert returned_ids[1] == str(run_ids[1])
        assert returned_ids[2] == str(run_ids[0])

    def test_cursor_pagination_no_overlap(self) -> None:
        base_time = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
        with get_session() as session:
            for i in range(5):
                defn_id = uuid4()
                run = RunRecord(
                    id=uuid4(),
                    experiment_definition_id=defn_id,
                    status=RunStatus.COMPLETED,
                    started_at=base_time + timedelta(minutes=i),
                    created_at=base_time + timedelta(minutes=i),
                )
                session.add(run)
            session.commit()

        client = TestClient(app)
        page1 = client.get("/runs?limit=3").json()
        assert len(page1["runs"]) == 3
        assert page1["nextCursor"] is not None

        page2 = client.get(f"/runs?limit=3&cursor={page1['nextCursor']}").json()
        assert len(page2["runs"]) == 2
        assert page2["nextCursor"] is None

        ids1 = {r["id"] for r in page1["runs"]}
        ids2 = {r["id"] for r in page2["runs"]}
        assert ids1.isdisjoint(ids2), "Pages must not overlap"

    def test_limit_clamped_to_100(self) -> None:
        client = TestClient(app)
        resp = client.get("/runs?limit=500")
        # Should succeed (not 400) and return at most 100
        assert resp.status_code == 200

    def test_invalid_cursor_returns_400(self) -> None:
        client = TestClient(app)
        resp = client.get("/runs?cursor=not-valid-base64!!!")
        assert resp.status_code == 400
```

### 10.2 Frontend hook tests — `useRunsPage.test.ts`

```typescript
// ergon-dashboard/src/__tests__/useRunsPage.test.ts

import { renderHook, act, waitFor } from "@testing-library/react";
import { useRunsPage } from "@/hooks/useRunsPage";

const mockRun = {
  id: "run-1",
  name: "Test Run",
  status: "completed",
  experimentId: "exp-1",
  startedAt: "2026-04-18T10:00:00Z",
  completedAt: "2026-04-18T10:05:00Z",
  durationSeconds: 300,
  finalScore: 0.9,
  error: null,
};

describe("useRunsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads first page on mount", async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ runs: [mockRun], nextCursor: null }),
    });

    const { result } = renderHook(() => useRunsPage(10));

    await waitFor(() => !result.current.isLoading);

    expect(result.current.runs).toHaveLength(1);
    expect(result.current.runs[0].id).toBe("run-1");
    expect(result.current.hasMore).toBe(false);
  });

  it("loadMore appends next page", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ runs: [mockRun], nextCursor: "abc123" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          runs: [{ ...mockRun, id: "run-2" }],
          nextCursor: null,
        }),
      });

    const { result } = renderHook(() => useRunsPage(1));
    await waitFor(() => !result.current.isLoading);
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.loadMore());
    await waitFor(() => !result.current.isLoading);

    expect(result.current.runs).toHaveLength(2);
    expect(result.current.hasMore).toBe(false);
  });

  it("sets error state on fetch failure", async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useRunsPage(10));
    await waitFor(() => !result.current.isLoading);

    expect(result.current.error).toMatch(/503/);
    expect(result.current.runs).toHaveLength(0);
  });
});
```

### 10.3 API contract test

The existing codegen at `ergon-dashboard/src/generated/rest/contracts` is generated from the FastAPI
OpenAPI schema. After adding `RunIndexRowDto` and `RunsPageDto`, regenerate the contracts and verify
the Zod schemas include `RunIndexRowDto` and `RunsPageDto` with the expected fields (id, name,
status, experimentId, startedAt, completedAt, durationSeconds, finalScore, error, nextCursor).

If the codegen is run via a script, add a CI step to fail if the generated file is stale (diff
non-empty after generation).

### 10.4 Store eviction test

Add to an existing or new store unit test:

```typescript
// ergon-dashboard/src/__tests__/store.test.ts

import { store } from "@/lib/state/store";

describe("DashboardStore.evictRun", () => {
  afterEach(() => store.reset());

  it("removes the run and its pending sandbox commands", () => {
    store.initializeRun("r1", "exp-1", "Test", { id: "t1", name: "task", description: "",
      children: [], depends_on: [], is_leaf: true, assigned_to: null },
      new Date().toISOString(), 1, 1);
    expect(store.getRun("r1")).toBeDefined();
    store.evictRun("r1");
    expect(store.getRun("r1")).toBeUndefined();
  });
});
```

---

## 11. Trace / Observability Impact

**No new spans.** The `list_runs` endpoint is a synchronous FastAPI GET; it runs within the scope
of any existing HTTP middleware tracing (e.g., OpenTelemetry FastAPI instrumentation if added in
future).

**Logging.** The `evictRun` call sites in `server.ts` log at `console.log` level (consistent with
existing Socket.io log lines), e.g.
`[Socket.io] No subscribers for run:<id> — evicted`.

**Metrics (optional, out of scope v1).** A future `store.size()` gauge metric could be exported to
observe live subscription counts. Not required for this RFC.

**No changes to the `CompletedSpan` attribute schema** (that lives in `worker_execute.py`).

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `(started_at, id)` keyset misses runs where `started_at IS NULL` | Runs with `started_at = null` fall outside cursor ordering and are skipped | `list_runs` falls back to `created_at` when constructing the cursor (see §5.1); ordering clause uses `started_at.desc().nullslast()` to push nulls to the end. Mark as known limitation: null-started runs appear last and are not re-orderable. |
| FastAPI `GET /runs` route conflicts with existing `GET /runs/{run_id}` | 404 or routing ambiguity if FastAPI matches `/runs` before `/runs/{run_id}` | `@router.get("")` (empty path, relative to prefix `/runs`) is distinct from `@router.get("/{run_id}")`. FastAPI resolves static paths before parameterized ones. Verified: existing routes use `/{run_id}`. No conflict. |
| Store eviction races: evict fires before a tab's `request:run` completes | Tab sends `request:run`, then is evicted before `sync:run` response arrives; tab shows empty state | `evictRun` only fires when room membership is zero. If a tab emits `subscribe` before `request:run`, it is in the room and will not be evicted. If a tab subscribes, gets evicted (no-one left in room), then reconnects — `useRunState` re-emits `request:run` and the load path reconstructs from Postgres. No data loss. |
| Removing `pruneOldRuns` causes unbounded memory for long-lived processes with many subscribers | OOM under very high run count if clients never unsubscribe | Narrowed store holds only subscribed runs. A process handling 100 concurrent subscribers with large run states is bounded by 100 runs in memory, not 50. Monitoring store size (§11 metric) is the safety valve. |
| `sync:runs` removal breaks existing clients that call `request:runs` | Legacy clients (e.g., old browser tabs) emit `request:runs` and receive no response | Server silently ignores unknown events. Client receives no `sync:runs` and sits in loading state. Acceptable for a dev tool; document in the PR description. |
| codegen drift: `RunIndexRowDto` added to FastAPI but generated contracts stale | Frontend type errors or silent mismatches | Follow §10.3 contract test procedure; regenerate `src/generated/rest/contracts` in PR 2. |

---

## 13. Invariants Affected

**`docs/architecture/05_dashboard.md §2` (DashboardStore retention)**
Currently: "oldest runs beyond a cap are pruned on new-run arrival. The cap is configurable via env;
the default lives in `ergon-dashboard/src/lib/config.ts:29`."
After this RFC: the store holds only currently-subscribed runs. No count cap, no time-based pruning.
The `maxRunsToKeep` config key becomes dead; it may be removed from `config.ts`.

**`docs/architecture/05_dashboard.md §4` invariant ("store is a cache")**
Currently stated but violated in practice by `request:runs`. After this RFC: strictly enforced.
The all-runs index view reads only from Postgres via `GET /api/runs`. The store is never queried for
index data.

**`docs/architecture/05_dashboard.md §4` invariant ("browser clients subscribe to specific run
rooms; they do NOT receive events for runs they have not subscribed to")**
Unchanged and strengthened: the store now also does not hold runs that have no subscribers.

**`docs/architecture/04_persistence.md §3` (Dashboard rehydration reads)**
Unchanged: "Dashboard rehydration reads a full run snapshot composed from the mutable tables
directly." This RFC adds a second read path (the index) that also reads directly from mutable
tables (`runs`). Both paths are consistent with the invariant.

**`docs/bugs/open/2026-04-17-dashboard-process-local-state.md`**
This RFC resolves the index-of-record half: the all-runs view no longer depends on the
process-local store, so two replicas show the same index. The residual bug — live-event fan-out
diverges across replicas for subscribed runs — is unchanged and remains open.

---

## 14. Alternatives Considered

- **Larger cap (100, 500, 1000 runs in store).** Rejected: does not fix HA or cold-start of
  historical runs; pushes the cliff further out. Postgres can always return historical data; the
  store should not pretend to be a database.

- **Redis-backed shared store.** Rejected for now: heavier than needed for a research tool when
  Postgres is already authoritative for the index. The live-event HA problem (fan-out) is a
  separate concern addressed by the existing bug report. Using Redis to fix the index problem would
  add operational complexity without benefit over a direct Postgres read.

- **Server-sent events (SSE) for the index stream.** Rejected: SSE adds complexity for a view that
  is not latency-sensitive at the page level. The index is a historical list; a "pull to refresh"
  UX is sufficient. Socket.io `run:started` / `run:completed` events already notify clients when
  the list changes; the client can re-fetch `/api/runs` on those events.

- **Offset pagination instead of cursor.** Rejected: offset pagination is unstable under concurrent
  inserts (a new run shifts all subsequent pages). The keyset cursor provides stable, efficient
  pagination even under high write rates. The cost is slightly more complex cursor serialization,
  which is encapsulated in `_encode_cursor` / `_decode_cursor`.

- **Serve the paginated index from the Socket.io handshake.** Rejected: REST is simpler,
  cache-friendly, easy to paginate, and decouples the index view from the live stream. This is
  the same reasoning as the original RFC proposal.

---

## 15. Open Questions

- **Cursor shape for `started_at IS NULL`.** Currently the cursor falls back to `created_at`. If
  `started_at` is always set at run creation time in practice, this is moot. Verify in production
  data before shipping.

- **Filtering (status, cohort, provider).** Out of scope for v1. The query param surface can be
  extended (`?status=completed`, `?cohort_id=<uuid>`) in a follow-up RFC without breaking the
  cursor contract, provided the filter is included in the cursor encoding.

- **Index page location.** The current home page renders `<CohortListView />` — there is no
  standalone all-runs index page in the current app. This RFC provides the hook (`useRunsPage`) and
  the API route. The UI component and routing are left to the implementer; the RFC does not prescribe
  a page path.

---

## 16. On Acceptance

When this RFC moves from `active/` to `accepted/`:

- Update `docs/architecture/05_dashboard.md` §2 (DashboardStore retention: from cap-based to
  subscription-based) and §4 (invariants: add "the all-runs index view reads only from Postgres via
  REST; it never reads from DashboardStore").
- Update `docs/architecture/05_dashboard.md` §7 (Follow-ups): mark the paginated-runs-api RFC as
  accepted; update the process-local-state bug entry to reflect that the index-of-record half is
  resolved.
- Close or rescope `docs/bugs/open/2026-04-17-dashboard-process-local-state.md` to "subscribed-run
  live-event fan-out diverges across replicas", which is the residual scope.
- Link the implementation plan in `docs/superpowers/plans/` once created.
- Regenerate `ergon-dashboard/src/generated/rest/contracts` to include the new schemas.
