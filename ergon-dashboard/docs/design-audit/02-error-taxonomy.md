# Error Taxonomy — Design Spec vs Current Implementation

Severity levels:
- **S1 — Missing surface**: An entire page/component from the spec doesn't exist.
- **S2 — Missing component**: A defined UI element within an existing page is absent.
- **S3 — Wrong styling**: The element exists but doesn't match the spec's visual treatment.
- **S4 — Wrong behavior**: The element exists but interactions differ from the spec.
- **S5 — Polish / refinement**: Minor spacing, typography, or color drift.

---

## Category 1: Missing Surfaces (S1)

### 1.1 — Global topbar with 5-tab navigation

**Spec**: Every page in the app has a shared 56px topbar with: `Ergon logo | Cohorts | Runs | Training | Models | Settings` nav tabs, global search bar (`⌕ Search cohorts, runs, tasks… ⌘K`), primary CTA button context-dependent (e.g., `+ New cohort`), and user avatar circle.

**Current**: No shared topbar component exists. `ClientLayout.tsx` only renders `ConnectionStatus`. Each page builds its own ad-hoc header:
- `CohortListView` has its own header with title + stats + filters but **no nav tabs, no search, no user avatar**.
- `RunWorkspacePage` builds a breadcrumb-based header with logo link, no nav tabs.
- `/training` page has no topbar at all.

**Impact**: Users have no way to navigate between Cohorts/Runs/Training/Models/Settings. The entire app feels like disconnected pages rather than a unified shell.

**Files**: `src/components/common/ClientLayout.tsx`, `src/app/layout.tsx`

---

### 1.2 — Cohort detail page (slide 04) — partial

**Spec**: Full cohort detail with breadcrumb, 5 summary metric tiles (Resolution, Runs pass/fail, Avg runtime, Avg tasks, Cost), score distribution chart (scatter/histogram/curve), and runs list with status filters.

**Current**: `CohortDetailView.tsx` exists (216 lines) but:
- **Missing**: Summary metric tiles (Resolution %, pass/fail bar, avg runtime, avg tasks, cost).
- **Missing**: Score distribution chart (scatter/histogram/curve toggle).
- **Missing**: Action buttons (`Compare | Re-run failed | Open in training`).
- Has a runs list but with less structure than the spec's card-in-card with filter segments.

**Files**: `src/components/cohorts/CohortDetailView.tsx`

---

### 1.3 — Edge states page (slide 08)

**Spec**: Defines 3 edge-state treatments: empty cohort (with CTA), failed run (error banner + replay), stale connection (socket fallback + unhandled mutation warning + no-graph placeholder).

**Current**: Basic error/loading states exist in individual components but **no designed empty states** matching the spec. No "Launch cohort" CTA, no replay-from-seq button, no styled connection-stale treatment, no "Run hasn't emitted nodes yet" placeholder.

**Files**: Scattered across `CohortListView`, `RunWorkspacePage`, `TaskWorkspace`

---

### 1.4 — Transitions (slides 09–11)

**Spec**: Three animated transitions with exact motion specs:
- T1: Cohort row → run workspace (shared element morph, 320ms)
- T2: Graph node → drawer (ring + slide, 260ms)
- T3: Event click → graph snapshot (per-node delta, 180ms)

**Current**: No View Transitions API, no FLIP animations. Navigation is standard Next.js page transitions. Drawer appears via CSS `slideInRight` animation (basic). No shared element morphing, no staggered rise.

**Files**: `src/app/globals.css` (has `slideInRight`/`slideOutRight` keyframes but they're simple slides, not the spec's multi-element choreography)

---

## Category 2: Missing Components (S2)

### 2.1 — Run header: inline key metrics (Tasks breakdown, Tokens, Cost, Score)

**Spec**: Run header shows `Tasks: 2·2·1·5 | Tokens: 142k | Cost: $0.18 | Score: —` in a stats row separated by a border-right divider from action buttons.

**Current**: Header shows `Tasks [total] | Turns [completed] | Score [%]` — **missing Tokens and Cost entirely**. The breakdown format is wrong (spec shows by-status counts, current shows totals). No divider styling between stats and buttons.

**Files**: `RunWorkspacePage.tsx` lines 303–312

---

### 2.2 — Graph floating controls: minimap

**Spec**: 200×130px minimap card top-right with colored rectangles per container + accent selection rectangle. Hides when drawer is open.

**Current**: React Flow's built-in `<MiniMap />` component is rendered in `DAGCanvas.tsx` but it uses React Flow's default rendering, not the spec's custom styled minimap with container-level colored blocks.

**Files**: `src/components/dag/DAGCanvas.tsx`

---

### 2.3 — Graph legend (bottom-left)

**Spec**: Floating card bottom-left with colored dots: `completed | running | ready | pending | failed`.

**Current**: No floating legend exists in the graph area. Status colors are implied by nodes but there's no key.

**Files**: `src/components/dag/DAGCanvas.tsx`

---

### 2.4 — Task drawer tab row

**Spec**: Drawer has a tab strip: `Overview | Transitions | Generations | Resources | Evals (badge) | Logs`.

**Current**: `TaskWorkspace.tsx` renders sections as stacked `WorkspaceSection` accordions — **no tab navigation**. All sections are visible at once in a scroll, not switched by tabs.

**Files**: `src/components/workspace/TaskWorkspace.tsx`

---

### 2.5 — Task drawer: Worker info section

**Spec**: Shows worker avatar square (initials), worker name (e.g., `explorer.B`), version kicker (`v0.7.2`), turn counter (`turn 3 of ≤ 8`).

**Current**: `TaskWorkspace` shows worker name as plain text in the header. No avatar, no version badge, no turn counter in the spec format.

**Files**: `src/components/workspace/TaskWorkspace.tsx`

---

### 2.6 — Task drawer: Current turn detail card

**Spec**: Card with tool call info: `tool · run_command | 2.1s · exit 1`, command line, error output in red mono.

**Current**: No "Current turn" card. Execution info exists in `CommunicationPanel` and `SandboxPanel` but not in the spec's format.

**Files**: `src/components/workspace/TaskWorkspace.tsx`, `src/components/panels/`

---

### 2.7 — Task drawer: Evals section with rich cards

**Spec**: Eval cards with: running judge (progress bar, streaming preview text), completed harness (score `0.84 / 1.0`, assertion count). `+ Attach eval` button.

**Current**: `EvaluationPanel.tsx` (82 lines) exists but is a minimal display. No progress bars, no streaming preview, no judge vs harness distinction, no attach button.

**Files**: `src/components/panels/EvaluationPanel.tsx`

---

### 2.8 — Task drawer: Resources section

**Spec**: File list with mono filename + version + size badges.

**Current**: `ResourcePanel.tsx` (234 lines) exists and shows resources, but styling doesn't match the spec's compact file-row format.

**Files**: `src/components/panels/ResourcePanel.tsx`

---

### 2.9 — Task drawer footer bar

**Spec**: Pinned footer with `Open in workspace` button + `Jump to live →` ghost button.

**Current**: No footer bar. The drawer has a close button but no workspace/jump actions.

**Files**: `src/components/workspace/TaskWorkspace.tsx`

---

### 2.10 — Activity stack: footer hint row

**Spec**: Below the bars: `Color = kind | Vertical stack = overlap | Click bar = select task/span | Click ● = lock graph above to that snapshot | Auto-tailing`.

**Current**: Bottom of the activity stack has event-type filter pills (`EXECUTION 3 | GRAPH 18 | TALK 1 | ARTIFACT 1 | EVALUATION 1 | CONTEXT 1 | SANDBOX 1`) instead of the spec's legend/hint row. These pills are functional filters not present in the spec at all.

**Files**: `src/features/activity/components/ActivityStackTimeline.tsx`

---

### 2.11 — Activity stack: snapshot pin + NOW cursor

**Spec**: When viewing a snapshot, an indigo vertical line + `SEQ N` pill appears on the timeline. The live cursor is a green pulsing line + `NOW` pill.

**Current**: The timeline has a blue vertical cursor line for current sequence but no styled `SEQ N` pill and no green `NOW` marker with pulse animation.

**Files**: `src/features/activity/components/ActivityStackTimeline.tsx`

---

### 2.12 — Graph: I/O ports on container edges

**Spec**: Small filled triangles on container edges marking input/output flow direction.

**Current**: No I/O port markers. Container nodes use React Flow handles but without the spec's triangle decorators.

**Files**: `src/features/graph/components/ContainerNode.tsx`

---

### 2.13 — Cohort list: table row structure

**Spec**: 7-column grid with: cohort name + mono ID, mono runs count, mono avg score, color-coded failure %, runtime + last activity, solid status pill, right chevron.

**Current**: `CohortListView` has a table but column structure and density differ. Missing the mono cohort_ID sub-line, missing the color-coded failure percentage, missing the right chevron.

**Files**: `src/components/cohorts/CohortListView.tsx`

---

## Category 3: Wrong Styling (S3)

### 3.1 — Activity stack: dark vs light

**Spec (slide 05–07)**: Activity stack dock uses **light** background (`#fafbfc`, border-top `var(--line)`). It's the same paper-family surface as the rest of the workspace. Header text is dark, bars are saturated.

**Current**: Activity stack uses **dark** background (`#070b12`, near-black), with light text. This was intentional in the recent visual pass and makes the bars pop, but it contradicts the spec's light treatment. The reference screenshots (slide-07-final.png) appear dark, suggesting the spec may have been updated — but the HTML source code clearly uses `#fafbfc`.

**Note**: The final rendered screenshots show a dark dock, so this may be an intentional design evolution. Worth confirming with the designer.

**Files**: `RunWorkspacePage.tsx` line 411, `ActivityStackTimeline.tsx`

---

### 3.2 — Activity bar colors: kind-based vs current palette

**Spec**: 7 distinct oklch kind colors (magenta, violet, amber, cyan, green, red, blue). Bars have **start marker circles** (circle at left edge with border).

**Current**: `ActivityBar.tsx` has `KIND_STYLES` mapping but the color values and set of kinds may not perfectly match the spec's 7 oklch values. Need to audit each one.

**Files**: `src/features/activity/components/ActivityBar.tsx`

---

### 3.3 — Node styling: compact vs verbose

**Spec**: Nodes are compact rectangles (~60px height) with: title (13px Inter semibold), status sub-line (10px JetBrains Mono), status dot (top-right 3.5px circle). Status color is fill + stroke, not badges.

**Current**: `LeafNode.tsx` (317 lines) renders much larger nodes with: status label text ("RUNNING"), task name, description, worker name, start time, and various icons. Nodes are visually heavy with multi-line content and orange/yellow decorative dots.

**Files**: `src/features/graph/components/LeafNode.tsx`, `src/features/graph/components/ContainerNode.tsx`

---

### 3.4 — Container styling: quiet chrome vs heavy borders

**Spec**: Containers use dashed stroke (`stroke-dasharray="4 4"`), semi-transparent fill (`rgba(255,255,255,0.55)`), with title (12px semibold) + sub-label (10px mono) in the header region. Running container gets a colored stroke (amber/etc). Very lightweight.

**Current**: `ContainerNode.tsx` uses depth-colored left borders, solid background, heavier visual treatment. The "chrome" is more prominent than the spec intends.

**Files**: `src/features/graph/components/ContainerNode.tsx`

---

### 3.5 — Fonts: Geist vs Inter + JetBrains Mono

**Spec**: `Inter` + `JetBrains Mono` loaded from Google Fonts.

**Current**: Layout loads `Geist` sans + mono via `next/font/local`, and `globals.css` body still has `font-family: Arial`. Neither `Inter` nor `JetBrains Mono` are loaded.

**Files**: `src/app/layout.tsx`, `src/app/globals.css`

---

### 3.6 — Status pill styling

**Spec**: Two pill variants:
- Outline: white bg, 1px border, color swatch dot, 11px/500.
- Solid: tinted bg, tinted border, tinted text (e.g., running = amber bg `oklch(0.96 0.04 80)`).

**Current**: `StatusBadge.tsx` (202 lines) exists and renders pills, but the color values and variant structure may not match the spec's oklch palette exactly.

**Files**: `src/components/common/StatusBadge.tsx`

---

### 3.7 — Run header breadcrumb density

**Spec**: Breadcrumb uses `›` separator, mono run ID, run name as `h1` (20px), status pill + `live · 1m 42s` kicker all in one tight row. Below that, stats are separated by a vertical `border-right` divider.

**Current**: Breadcrumb uses `/` separator, different typography density, stats row doesn't have the divider treatment.

**Files**: `RunWorkspacePage.tsx` lines 268–380

---

### 3.8 — Workspace drawer width

**Spec**: Drawer is `460px` wide.

**Current**: Workspace region is `360px` wide (`w-[360px]`).

**Files**: `RunWorkspacePage.tsx` line 454

---

### 3.9 — Graph stage background

**Spec**: Dot-grid pattern: `radial-gradient(circle, rgb(15 23 42 / 0.04) 1px, transparent 1px)` at `22px 22px` on `var(--paper)`.

**Current**: React Flow's built-in `<Background />` component with dot pattern. May not match the exact dot size/opacity/spacing.

**Files**: `src/components/dag/DAGCanvas.tsx`

---

### 3.10 — Card shadow and border radius

**Spec**: `--radius: 10px`, `--shadow-sm: 0 1px 2px rgb(12 17 24 / 0.04)`, `border: 1px solid var(--line)`.

**Current**: Various border-radius values used inline. Some match, some use Tailwind defaults.

**Files**: Various components

---

## Category 4: Wrong Behavior (S4)

### 4.1 — Drawer is right overlay, not page section

**Spec**: Drawer overlays the graph stage from the right edge (inside the graph's coordinate space). Graph reflows left when drawer opens. Drawer has `shadow-pop`.

**Current**: Recent visual pass moved it to a right-side overlay (`absolute right-4 top-4`), which is closer. But it's positioned relative to `<main>` not the graph stage, and the graph does NOT reflow.

**Files**: `RunWorkspacePage.tsx` lines 452–470

---

### 4.2 — Event click → graph snapshot lock

**Spec**: Clicking an event marker (●) in the timeline locks the graph above to that sequence point. The timeline continues tailing live. A snapshot pin (indigo) appears at the locked sequence.

**Current**: Clicking an activity switches to timeline mode and changes `currentSequence`, but the visual treatment (pin, split between locked graph and live tail) doesn't match. There's no visible distinction between "graph locked to seq X" and "just scrolled to seq X".

**Files**: `RunWorkspacePage.tsx` `handleActivityClick`, `ActivityStackTimeline.tsx`

---

### 4.3 — Depth selector integration

**Spec**: Floating card in graph stage with buttons `1 | 2 | 3 | all`.

**Current**: `DepthSelector.tsx` exists (157 lines) and is rendered by `DAGCanvas`, but it's part of a `RunStatusBar`-adjacent filter bar above the graph, not a floating card inside the graph canvas.

**Files**: `src/features/graph/components/DepthSelector.tsx`, `src/components/dag/DAGCanvas.tsx`

---

## Category 5: Polish / Refinement (S5)

### 5.1 — Activity stack left rubric

**Spec**: 140px left column with "Concurrent activity / Bars stack only when they overlap." text block.

**Current**: Left rail has "Concurrent activity / Bars stack only / when they overlap" but sizing and typography may be cramped (noted in the PR description).

---

### 5.2 — Activity stack time axis

**Spec**: Mono 10px timestamps in an 8-column grid with `· now` suffix on the current time slot.

**Current**: Time axis exists but the density and styling may differ.

---

### 5.3 — Graph status bar overlap

**Spec**: No separate filter bar above the graph. Filters are floating cards inside the graph canvas.

**Current**: `RunStatusBar` renders as an absolute-positioned bar that overlaps with the graph (noted in the PR description).

---

### 5.4 — Segmented controls

**Spec**: `.seg` component — inline-flex, 1px border, 7px radius, 2px padding, active tab has card bg + shadow.

**Current**: Tab controls use Tailwind classes that approximate this but may not match the exact padding/radius/shadow values.

---

## Summary counts

| Severity | Count |
|----------|-------|
| S1 — Missing surface | 4 |
| S2 — Missing component | 13 |
| S3 — Wrong styling | 10 |
| S4 — Wrong behavior | 3 |
| S5 — Polish | 4 |
| **Total** | **34** |
