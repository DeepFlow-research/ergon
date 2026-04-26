# P4 — Interactions + Polish

**Goal**: Add transition animations, wire up keyboard shortcuts, responsive adjustments, and final pixel audit.

**Addresses**: 1.4 (transitions), 4.2 (snapshot lock), remaining S5 items

---

## Task 4.1 — Drawer enter/exit animation

**File**: `src/app/globals.css`, `RunWorkspacePage.tsx`

Current `slideInRight` / `slideOutRight` animations exist but are basic. Enhance:

1. **Drawer enter** (260ms): slides from right edge, starts 28px offset and 55% opacity → settles at 0 offset, 100% opacity. Uses `cubic-bezier(.22, 1, .36, 1)`.
2. **Selection ring** on the clicked node appears in 80ms (independent of drawer).
3. **Graph reflow**: When drawer opens, the graph stage should compress left by the drawer width. This can be done by adding a right margin/padding to the React Flow container when `isInspectorOpen`.

```css
@keyframes drawerEnter {
  from { transform: translateX(28px); opacity: 0.55; }
  to { transform: translateX(0); opacity: 1; }
}
@keyframes drawerExit {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(28px); opacity: 0; }
}
```

---

## Task 4.2 — Snapshot lock visual distinction

**Files**: `RunWorkspacePage.tsx`, `ActivityStackTimeline.tsx`

When the user clicks an event marker (●) in the timeline:

1. Graph locks to that sequence (existing behavior via `handleActivityClick`).
2. **Visual indicators**:
   - Header chip shows `graph · seq N · TIME` in mono (existing partial implementation).
   - Activity stack gets indigo snapshot pin (Task 2.3).
   - The live NOW cursor continues to pulse at the right edge.
3. **Esc key** clears the snapshot lock (returns graph to live).
4. **Arrow keys** (←/→) when graph is locked should step ±1 affected node in the mutation log.

---

## Task 4.3 — Keyboard shortcuts completion

**File**: `RunWorkspacePage.tsx` (already has keydown handler)

Verify all shortcuts from the spec:
- `Esc`: clear selection → clear snapshot lock → clear filter (cascade)
- `t` / `T`: toggle live/timeline
- `e` / `E`: toggle event stream
- `1-6`: filter by status (existing)
- `⌘K`: focus search (when implemented)
- `⌘D`: open/close drawer (if a node is selected)

---

## Task 4.4 — Cohort row → run workspace transition (T1)

This is the most complex transition. For MVP:

1. **Navigate** from `/cohorts/:id` to `/cohorts/:id/runs/:runId` using Next.js router.
2. **During navigation**: the clicked row gets an accent outline (80ms) before the page change.
3. **On the run page**: the header animates in from a compact state (row height → full header height) over 320ms.
4. **Graph + activity stack** rise from below with 60ms stagger.

Implementation options:
- **View Transitions API** (if browser support is acceptable): Use `document.startViewTransition()` with shared element names on the row chip and header chip.
- **FLIP technique**: Measure row position before navigation, apply inverse transform on mount, animate to identity.
- **Simpler fallback**: Just do a cross-fade between pages. The spec says `reducedMotion: "Cross-fade only · 120 ms · no rise/morph"` — this can be the default implementation for now, with enhanced animation as a follow-up.

---

## Task 4.5 — Event marker → snapshot transition (T3)

When clicking an event marker:
1. Snapshot pin appears on timeline (180ms).
2. Graph nodes whose status differs at the snapshot sequence animate their fill color (180ms per node delta).
3. Nodes that don't change stay still.

Implementation: Compare `displayState` at live vs at snapshot sequence. For each node where status changed, apply a CSS transition on `background-color` and `border-color`.

---

## Task 4.6 — Responsive adjustments

The spec is designed for 1920×1080 and is dense. For smaller viewports:

- **< 1440px**: Stats row in run header wraps or becomes a dropdown.
- **< 1280px**: Drawer collapses to a bottom sheet instead of right panel.
- **< 1024px**: Activity stack collapses to a thin strip (just the NOW cursor).
- **< 768px**: Topbar hamburger menu for nav tabs.

These are suggestions — the spec doesn't explicitly define responsive breakpoints. Implement as progressive enhancement.

---

## Task 4.7 — Final pixel audit

After all phases, do a side-by-side comparison with the spec screenshots:

1. Open the spec deck in a browser: `open /tmp/ergon-design-spec/index.html`
2. Screenshot each slide at 1920×1080.
3. Compare with the dashboard at the same viewport size.
4. Document any remaining deltas.

Key areas to check:
- [ ] Font rendering (Inter + JetBrains Mono at correct weights)
- [ ] Color token accuracy (oklch values rendering as expected)
- [ ] Spacing / padding values
- [ ] Border radius consistency
- [ ] Shadow values
- [ ] Animation timing

---

## Task 4.8 — Extended visual debugger screenshots

Add new e2e test screenshots to `tmp/visual-debugger/`:

```
cohort-list.png         — Full cohort list page with topbar
cohort-detail.png       — Cohort detail with metric tiles + chart
run-workspace-live.png  — Run workspace in live mode (updated)
run-workspace-drawer.png — Run workspace with drawer open + snapshot pin
graph-compact.png       — Zoomed graph showing compact node styling
activity-stack-full.png — Activity stack with NOW cursor + hint row
empty-cohort.png        — Empty cohort state
failed-run.png          — Failed run state
```

Update `activity-stack.spec.ts` to capture these, gated behind `VISUAL_DEBUGGER_SCREENSHOTS=1`.

---

## Verification

After P4:
- [ ] Drawer animates in/out with spec timing
- [ ] Graph reflows when drawer opens
- [ ] Snapshot lock has visible pin + header chip
- [ ] Arrow keys step through snapshots
- [ ] Cross-fade on page transitions (at minimum)
- [ ] All 8 new screenshots captured
- [ ] `npm run typecheck` passes
- [ ] Full e2e suite passes
- [ ] Side-by-side with spec screenshots shows high fidelity
