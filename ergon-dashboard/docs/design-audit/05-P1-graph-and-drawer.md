# P1 — Graph Stage + Drawer Rework

**Goal**: Bring the graph canvas, node rendering, container chrome, floating controls, and task drawer into spec alignment.

**Addresses**: 2.1 (stats), 2.2 (minimap), 2.3 (legend), 2.4 (tabs), 2.5 (worker), 2.6 (turn card), 2.7 (evals), 2.8 (resources), 2.9 (footer), 2.12 (I/O ports), 3.3 (nodes), 3.4 (containers), 3.8 (drawer width), 3.9 (graph bg), 4.1 (drawer position), 4.3 (depth selector)

---

## Task 1.1 — Compact leaf node styling

**File**: `src/features/graph/components/LeafNode.tsx` (317 lines → target ~120)

Current nodes are tall, verbose cards with status label text, description, worker, timestamps, and decorative dots. The spec wants:

- **Height**: ~50–60px
- **Content**: Task name (13px Inter 600) + status sub-line (10px JetBrains Mono) in status color
- **Status indicator**: 3.5px circle, top-right corner, filled with status color
- **Fill**: Status-tinted background (e.g., running = `oklch(0.97 0.04 80)`)
- **Stroke**: Status-tinted border (e.g., running = `oklch(0.85 0.10 80)`)
- **Border radius**: 6px
- **Selection**: 2px indigo ring at 2px offset (via `--accent`)

Remove: status text label ("RUNNING"), description line, worker name, start timestamp, decorative triple-dots.

Status color map (from deck.js `NODE` function):
```
completed: [bg: "oklch(0.96 0.04 155)", border: "oklch(0.85 0.10 155)", text: "oklch(0.40 0.12 155)"]
running:   [bg: "oklch(0.97 0.04 80)",  border: "oklch(0.85 0.10 80)",  text: "oklch(0.42 0.12 65)"]
ready:     [bg: "oklch(0.97 0.03 240)", border: "oklch(0.86 0.08 240)", text: "oklch(0.40 0.12 240)"]
pending:   [bg: "#ffffff",              border: "#e2e6ec",               text: "#98a2b1"]
failed:    [bg: "oklch(0.97 0.04 22)",  border: "oklch(0.85 0.10 22)",  text: "oklch(0.40 0.16 22)"]
```

---

## Task 1.2 — Lightweight container chrome

**File**: `src/features/graph/components/ContainerNode.tsx` (157 lines)

Current: solid background with colored left border by depth. Spec wants:

- **Fill**: `rgba(255,255,255,0.55)` (semi-transparent white)
- **Stroke**: `#cdd3dc` dashed (`stroke-dasharray: 4 4`); running containers get status-colored stroke
- **Header**: container title (12px Inter 600) left, sub-label (10px mono, muted) right-aligned
- **Border radius**: 8px
- **No depth-colored left border** — depth is conveyed by nesting level only

Remove the `getLevelColor` depth border. Container "running" state gets an amber border instead of dashed gray.

---

## Task 1.3 — Floating graph controls

**File**: `src/components/dag/DAGCanvas.tsx`

Replace the current status filter bar above the graph with floating control cards **inside** the graph stage:

**Top-left cluster** (z-5, flex row, gap-8px):
1. **Zoom card**: `＋ | − | ⌂` icon buttons in a `.card` with 4px padding
2. **Depth card**: `DEPTH` section-title + segmented `1 | 2 | 3 | all` buttons
3. **Search card**: `SEARCH` section-title + mono placeholder `find a task…`

**Top-right** (z-5):
- **Minimap**: 200×130px card with custom rendering (colored rectangles per container status + accent selection rect). Hide when drawer is open.

**Bottom-left** (z-5):
- **Legend**: card with flex row of colored dots + labels: `completed | running | ready | pending | failed`

Move `RunStatusBar` (currently absolute-positioned above graph) into the floating control cluster or remove it — the status counts are redundant with the legend and the header stats.

---

## Task 1.4 — Run header stats row

**File**: `src/components/run/RunWorkspacePage.tsx` (header section, lines ~302–313)

Current stats: `Tasks [total] | Turns [completed] | Score [%]`

Spec stats: `Tasks: 2·2·1·5 | Tokens: 142k | Cost: $0.18 | Score: —`

Changes:
- Tasks shows breakdown by status: `completed · running · ready · pending` (dot-separated)
- Add `Tokens` (from `runState` if available, else `—`)
- Add `Cost` (from `runState` if available, else `—`)
- Keep `Score`
- Stats block has `border-right: 1px solid var(--line)` + `padding-right: 8px` separating it from action buttons
- Each stat: `section-title` label (11px uppercase faint) + `mono` value (14px ink)

---

## Task 1.5 — Task drawer: width, position, tab navigation

**File**: `src/components/workspace/TaskWorkspace.tsx`

### Width
Change from `w-[360px]` to `w-[460px]` in `RunWorkspacePage.tsx` (line 454).

### Position
Drawer should be positioned inside the graph stage `<section>`, not inside `<main>`. This means moving the workspace-region section to be a child of graph-region, with `position: absolute; top: 16px; right: 16px; bottom: 16px;`.

### Tab navigation
Replace the stacked `WorkspaceSection` accordion pattern with a tab strip:

```
Overview | Transitions | Generations | Resources | Evals (N) | Logs
```

- Active tab: bottom 2px border in `var(--ink)`, no border-radius
- Inactive: ghost button styling
- Evals tab shows a count badge pill

Each tab renders its corresponding panel. Only one panel visible at a time.

### Header structure
```
[section-title: TASK WORKSPACE]  [Pin button] [Close button]
[h3: task_name]  [status pill]
[mono caption: task / parent / name · seq N]
```

---

## Task 1.6 — Task drawer: content sections

### Worker section
- 24×24 rounded-6px avatar square (dark bg, white initials)
- Worker name (font-weight 500)
- Version kicker (mono 10px in `var(--paper-2)` bg)
- Turn counter right-aligned: `turn N of ≤ M`

### Transitions section
- Status pill pairs: `pending → ready` with sequence + time on the right
- Trigger description sub-line (11px muted, indented)

### Current turn section
- Card with `var(--paper-2)` background
- Header: `tool · tool_name` + `duration · exit code` right-aligned
- Command line in mono
- Error output in mono, colored `oklch(0.40 0.16 22)` (failed red)

### Evals section
- Judge card: status dot + eval name + status pill, kicker with model info, progress bar, streaming preview text (truncated mono)
- Harness card: status dot + eval name + passed pill, kicker with type info, score display (`0.84 / 1.0`), assertion count
- `+ Attach eval` ghost button

### Resources section
- File rows: mono filename + `version · size` right-aligned, each in a 6px-radius bordered row

### Footer bar
- Pinned to bottom of drawer
- `var(--paper)` background, top border
- `Open in workspace` button + `Jump to live →` ghost button right-aligned

---

## Task 1.7 — Graph edge styling

**File**: `src/components/dag/edges/GraphDependencyEdge.tsx`

Edges should use:
- Default: `#cdd3dc` stroke, 1.5px width
- Active (connected to running container): status color
- Bezier curves with configurable curvature
- Arrow markers at endpoints

---

## Verification

After P1:
- [ ] Nodes are compact (≤60px height) with correct status fills
- [ ] Containers use dashed borders, no depth-colored left bar
- [ ] Floating controls (zoom, depth, search, minimap, legend) are inside graph canvas
- [ ] Drawer is 460px, positioned inside graph stage, has tabs
- [ ] Drawer sections render correctly per active tab
- [ ] `npm run typecheck` passes
- [ ] `activity-stack.spec.ts` still passes (may need selector updates for new DOM structure)
- [ ] New screenshot: `graph-canvas-compact.png` shows compact nodes
