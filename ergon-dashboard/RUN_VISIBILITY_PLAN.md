# Run Workspace Visibility & Visual Design Plan

Goal: raise every dimension of the run-viewing workspace from current scores to **≥ 8/10**.
Anchor principles:
1. **No silent data dropping** — if an event crosses the wire, the user can either see it or see that it was filtered.
2. **Transitions are first-class** — users can answer "what happened between T₁ and T₂ on this task?" without reading server logs.
3. **Visual fidelity** matches `fractal-clones/slot-1/fractal-client` (layered status badges with white borders, HSL-modulated node colors, corner status icons, framer-motion micro-animations, reusable primitives).

Current scores (from review 2026-04-16):

| Dimension | Current | Target |
|---|---|---|
| Overall run status | 7 | 9 |
| Per-task status | 7 | 9 |
| Transitions between states | 4 | 8 |
| Unified event stream | 3 | 8 |
| Timeline scrubber fidelity | 5 | 9 |
| Generations view | 7 | 9 |
| Mode switching (Live ↔ Timeline) | 6 | 8 |
| **Overall** | **5** | **8+** |

---

## Cross-cutting foundations

These land first because every workstream depends on them.

### F1. Unified event contract (`RunEvent`)
**Why:** today 13 event kinds arrive via distinct Socket.io channels and land in separate slices of state. A unified timeline is impossible until we can enumerate them.

**Change:**
- Introduce `RunEvent` discriminated union in `src/lib/contracts/runEvents.ts`:
  ```ts
  type RunEvent =
    | { kind: "workflow.started"; at: string; runId: string; ... }
    | { kind: "task.status_changed"; at: string; taskId: string; from: TaskStatus; to: TaskStatus; trigger: TaskTrigger; ... }
    | { kind: "generation.turn"; at: string; taskExecutionId: string; turnIndex: number; ... }
    | { kind: "sandbox.command"; ... }
    | { kind: "thread.message"; ... }
    | { kind: "task.evaluation"; ... }
    | { kind: "resource.published"; ... }
    | { kind: "graph.mutation"; ... };
  ```
- Store in `WorkflowRunState.events: RunEvent[]` (append-only, sorted by `at` then `sequence`).
- `DashboardStore` keeps existing per-kind slices derived from this log so panel code doesn't churn.

**Acceptance:** every Socket.io event updates `events[]`; `events.length` is monotonically non-decreasing during a session.

### F2. Expose `TaskTrigger` on every status change
**Why:** the transitions dimension sits at 4/10 because `TaskTrigger` is defined but never rendered. Without the trigger, a status change is a noun, not a verb.

**Change:**
- Server-side: include `trigger: TaskTrigger` on `dashboard/task.status_changed` and on every `node.status_changed` graph mutation (already in wire contract; confirm backend emits).
- Client reducer (`graphMutationReducer.ts:117`): persist `lastTrigger` on `TaskState` and push a `task.status_changed` RunEvent.
- **Do not silently drop** unknown triggers — emit a `task.status_changed` with `trigger: "unknown"` and surface a subtle warning chip.

### F3. Eliminate silent no-ops in the reducer
**Why:** current `graphMutationReducer.ts:70-78` silently returns `state` for `edge.removed`, `edge.status_changed`, `annotation.set`, `annotation.deleted`. Scrubbing past them advances the slider with zero visual effect.

**Change:**
- Implement `edge.removed`, `edge.status_changed`: update `dependsOnIds` / edge style map.
- Implement `annotation.*`: store `annotationsByTarget: Map<string, Annotation[]>`, surface via a subtle margin marker on the node.
- Any truly unhandled type raises a visible `UnhandledMutationPill` in the timeline strip (never silent).

**Acceptance test:** a scrub over a run containing every mutation type produces a non-empty diff of `runState` at each step (write a property test).

---

## Dimension-by-dimension plan

### D1. Overall run status (7 → 9)

**Problem:** one badge + 4 tiles. No breakdown of pending/ready/running/completed.

**Changes:**
- Replace the 4-tile dl in `RunWorkspacePage.tsx:185‑210` with a **segmented status bar** (slot-1-style inverted colored pills):
  - `RUNNING 3 · READY 5 · PENDING 12 · COMPLETED 40 · FAILED 1 · CANCELLED 0`
  - Each segment uses the same color language as the per-task badges (see D2).
  - Width proportional to count; hover shows the task list filtered by status.
- Add **runtime progress bar** next to the `StatusBadge` showing wall-clock elapsed / estimated (if an ETA is available from cohort history).
- Add **live/stale indicator**: pulse-dot when `isSubscribed`, grey dot when REST fallback.

**Citations from slot-1:** the TaskStatusBadge inverted-color pattern (`bg-yellow-400` + `text-white`) and the `size-3` StatusIcon scaling.

### D2. Per-task status (7 → 9)

**Problem:** nodes show status via color but lack the visual polish of slot-1 (corner badges, HSL-modulated fills, white rings).

**Changes in `features/graph/components/LeafNode.tsx`, `ContainerNode.tsx`:**
- Adopt slot-1's **corner status badge** pattern:
  ```tsx
  <div
    style={{ backgroundColor: statusColor }}
    className="absolute -top-0.5 right-0.5 z-30 flex size-[22px]
      items-center justify-center rounded-full border-2 border-white
      shadow-sm transition-transform hover:scale-110"
  >
    <StatusIcon status={task.status} className="size-3 text-white" />
  </div>
  ```
- **HSL-modulated fill** for container nodes based on child completion %:
  ```ts
  // Lift slot-1/src/features/workflow-graph/utils/color-utils.tsx
  adjustLightnessBasedOnPercentage(baseHue, completedChildren / totalChildren * 100)
  ```
- Standard icon set: `CheckCircle` (completed), `XCircle` (failed), `Loader2` spinning (running), `Clock` (pending), `CircleDashed` (ready), `Ban` (cancelled).
- Status color tokens centralized in `tailwind.config.ts`:
  ```
  status.pending:   slate-400
  status.ready:     sky-400
  status.running:   amber-400 (animated)
  status.completed: emerald-500
  status.failed:    rose-600
  status.cancelled: zinc-500
  ```
- Running nodes get a **framer-motion pulsing ring** (scale 0.9→1.1, 1.4s cycle — lifted from slot-1's `scaleUpDown` keyframe).

### D3. Transitions between states (4 → 8) ⭐ biggest lift

**Problem:** no trigger rendering, intermediate transitions squashed onto one `status` field, no per-task history.

**Changes:**
1. **New primitive: `<TransitionChip trigger={...} from={...} to={...} at={...} />`**
   - Location: `src/components/common/TransitionChip.tsx`.
   - Shape: `PENDING ──dependency_satisfied──▶ READY · 12:04:07.142`.
   - Color comes from the **destination** status.
2. **TaskWorkspace transition log panel** — a chronological list of every status change for the selected task, rendered as stacked `TransitionChip`s with gap-timing annotations ("held in READY for 4.3s").
3. **Reducer persists history** (`TaskState.history: Array<{from, to, trigger, at}>`) built from `RunEvent`s, not derived on render.
4. **Hover on a node in the DAG** briefly overlays its most recent transition chip (uses F1's event log).

**Acceptance:** for any completed task, I can read the exact chain `pending → ready → running → completed` with triggers and wall-clock gaps without leaving the page.

### D4. Unified event stream (3 → 8) ⭐ biggest lift

**Problem:** zero chronological view across event kinds.

**Changes:**
- **New panel: `<UnifiedEventStream>`** docked in the inspector or as a collapsible right-rail, driven by `WorkflowRunState.events`.
- Row shape (inspired by slot-1 chat-chip density):
  ```
  [12:04:07.142] [task.status_changed] task/abc  PENDING → READY  (dependency_satisfied)
  [12:04:07.203] [generation.turn]     task/abc  turn 0  tools: read_file, grep
  [12:04:09.887] [sandbox.command]     sbx/xyz   uv run pytest    exit=0  (2.1s)
  [12:04:10.001] [task.status_changed] task/abc  RUNNING → COMPLETED  (execution_succeeded)
  ```
- **Filter toolbar** (multi-select chip row): filter by event kind, task, worker, severity. Filters never hide events silently — a `N events hidden` counter is always visible with a clear-all button.
- **Jump-to-graph**: click a row ⇒ select the related task in the DAG and scrub `MutationTimeline` to the matching sequence.
- Virtualized list (`react-window`) so long runs stay performant.

### D5. Timeline scrubber fidelity (5 → 9)

**Problem:** scrubber replays only graph mutations; sandbox/thread/eval/generation invisible; silent no-op segments.

**Changes in `MutationTimeline.tsx` (rename → `RunTimeline`):**
- Source changes from `mutations[]` to `events[]` (F1). Scrubbing now replays the entire run, not just the DAG slice.
- **Stacked lane track** (multi-row D3.js-lite SVG) under the slider, one lane per event kind, event markers colored by kind. Slot-1-style.
- **Sparkline of task.status_changed events** on the main slider so you see bursts of activity at a glance.
- `currentMutation` detail strip becomes `<CurrentEventDetail event={events[i]}>` with kind-specific rendering (status change ⇒ `TransitionChip`; generation turn ⇒ mini `TurnCard`; sandbox command ⇒ command + exit code).
- Visible marker for any event whose reducer is a no-op (D-foundation F3 ensures this is rare; when it happens, a `⚠ unhandled: edge.removed` chip appears).
- **Preserve existing strengths:** wall-clock-proportional playback, 1x–10x speeds, snapshot cache every 50 events (bump to 100 given richer events).

### D6. Generations view (7 → 9)

**Problem:** turns are polished but orphaned — not linked to graph transitions.

**Changes in `GenerationTracePanel.tsx`:**
- Each `TurnCard` gains a **"Jump to graph at this turn"** link that sets `currentSequence` in `RunTimeline` and flashes the owning task.
- **Correlation indicator**: if a turn's final tool-call immediately precedes a `task.status_changed` to `completed`/`failed`, render a subtle right-edge bracket `]── caused: RUNNING → COMPLETED`.
- Adopt slot-1 typography: `SuisseIntl` (or project-equivalent), `text-base font-semibold` for worker name, `text-xs bg-ai8-soft-gray px-1 py-0.5 rounded-md` for policy-version pills.
- Token-count / latency chip on each turn header when available.
- Sticky worker-group headers in multi-agent mode (currently a plain `<h4>`).

### D7. Mode switching (6 → 8)

**Problem:** toggle doesn't tell you what the timeline is actually replaying; selection-reset notice is good but limited.

**Changes in `RunWorkspacePage.tsx:167‑178`:**
- Toggle becomes a **segmented control**: `[Live] [Timeline] [Diff]` (Diff mode: pick two sequences, show node-level delta — nice-to-have but cheap once F1 exists).
- Under the toggle in `Timeline` mode, a **"Replaying N events across K kinds"** caption with a `(configure)` link that opens a kind-filter popover.
- Timeline mode shows a **"timeline cursor is at T+12.4s of 00:01:43 wall-clock"** chip next to the `StatusBadge`.
- Keyboard shortcuts (`[` `]` step, `space` play/pause, `L` toggle live) — slot-1 has precedent for this level of polish.

---

## Visual design refresh (project-wide)

Lifted wholesale from slot-1:
- **Status color tokens** (D2) replace ad-hoc Tailwind colors.
- **Layered-badge pattern** (outer white-ringed circle + inner icon) for every status surface: nodes, row dots, chat chips.
- **Framer-motion** micro-interactions: `fade-in 0.8s`, `scaleUpDown 1.4s`, `accordion-up/down 0.2s`.
- **Gradient accent borders** (`border-bluish-gradient` at 56.89°) for hero cards (run header, inspector title).
- **Shadow vocabulary**: `shadow-first-level-top-corner`, `shadow-second-level-bottom-corner` for hierarchy depth (only on container nodes).
- **Typography scale**: inherit slot-1's `SuisseIntl` or pick a single geometric sans and standardize `text-[10px]` / `text-xs` / `text-sm` / `text-base` usage — current code mixes `text-[10px]` and `text-xs` without system.
- **Reusable primitives** to create under `src/components/common/`:
  - `StatusBadge` (already exists — extend to accept `compact` + `inverted` props à la slot-1).
  - `StatusIcon` (new; one switch on `TaskStatus`).
  - `TransitionChip` (D3).
  - `Chip` (generic tag/token; reuse for policy version, worker name, event kind).
  - `Pulse` (animated-ring wrapper for running indicators).

---

## Workstream ordering & rough effort

1. **Foundations (F1, F2, F3)** — unblocks everything. Medium. Changes span backend event emitters, `lib/types.ts`, reducer, store.
2. **D2 visual refresh** (status tokens, corner badges, HSL fills) — small-medium, purely FE. High visual ROI, safe to ship independently.
3. **D3 transition log** — small once F1+F2 land.
4. **D4 unified event stream** — medium; needs virtualization + filtering.
5. **D5 timeline refactor** — medium; piggy-backs on F1 + D4.
6. **D6 generation correlation** — small; needs D5 in place for cross-linking.
7. **D1 status bar + D7 segmented control** — small; polish pass after the data story is solid.
8. **Project-wide visual refresh** — runs in parallel with D2 onward.

## Non-goals (explicit, to avoid scope creep)
- No change to backend persistence format; all work sits in event contracts + FE.
- No rewrite of `DAGCanvas` layout (XYFlow + Dagre stays).
- No new dependencies beyond `framer-motion` (already available elsewhere in the org) and `react-window` (for virtualization).

## Definition of done
- Every dimension above has a self-check: a scripted playback of `tests/fixtures/full-lifecycle-run.json` shows, for a single selected task, the full `pending → ready → running → completed` chain with triggers, the causing generation turn, the owning sandbox command, and the final evaluation — all reachable within two clicks from the DAG node.
- `pnpm run check:fe` passes.
- Playwright scenario `run-workspace-visibility.spec.ts` asserts no `events` are silently dropped during a scripted mutation replay.
