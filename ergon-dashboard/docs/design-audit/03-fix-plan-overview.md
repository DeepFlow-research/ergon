# Fix Plan — Overview

## Phasing strategy

Work is split into 5 phases, each shippable independently. Phases are ordered by **structural impact** (foundations first, polish last), so that later phases build on correct bones.

| Phase | Name | Effort | Scope |
|-------|------|--------|-------|
| P0 | Design system foundations | 1 day | Tokens, fonts, shared topbar, app shell |
| P1 | Graph + drawer rework | 1–2 days | Node styling, containers, drawer, floating controls |
| P2 | Activity stack alignment | 1 day | Light/dark decision, kind colors, NOW/snapshot pins, hints |
| P3 | Cohort surfaces | 1–2 days | Cohort list columns, cohort detail metrics/chart, edge states |
| P4 | Interactions + polish | 1 day | Transitions, keyboard shortcuts, responsive, final pixel audit |

Each phase has its own detailed plan document below.

## Dependencies

```
P0 ──→ P1 ──→ P2
  ╲              ╲
   ──→ P3        ──→ P4
```

P0 must land first (everything depends on the shared shell and token system). P1 and P3 can run in parallel after P0. P2 depends on P1 (graph stage layout affects activity stack positioning). P4 is the final sweep.

## Principles

1. **Don't break existing tests.** Run `npm run typecheck` + focused e2e tests after every meaningful file change.
2. **Extend the visual debugger screenshots.** Add new screenshot assertions for each new surface (cohort list, cohort detail, topbar) so regressions are caught.
3. **Use CSS custom properties from the spec**, not hardcoded hex in Tailwind classes. Centralize tokens in `globals.css` and reference them via `var(--token)`.
4. **Prefer editing existing components** over creating new ones. Only create new files for genuinely new surfaces (e.g., the global Topbar).

## Files to create

| File | Purpose |
|------|---------|
| `src/components/shell/Topbar.tsx` | Global navigation bar |
| `src/components/shell/AppShell.tsx` | Layout wrapper with topbar + content area |
| (none else new — all other work is editing existing files) |

## Files to substantially edit

| File | Changes |
|------|---------|
| `src/app/globals.css` | Add full design token set, remove Arial fallback, Inter + JB Mono |
| `src/app/layout.tsx` | Swap Geist for Inter + JetBrains Mono, wrap in AppShell |
| `src/components/common/ClientLayout.tsx` | Integrate Topbar, or replace with AppShell |
| `src/components/run/RunWorkspacePage.tsx` | Header → use Topbar, drawer width, stats row, graph layout |
| `src/features/graph/components/LeafNode.tsx` | Compact node styling per spec |
| `src/features/graph/components/ContainerNode.tsx` | Dashed, lightweight container chrome |
| `src/components/dag/DAGCanvas.tsx` | Floating controls, legend, minimap styling |
| `src/components/workspace/TaskWorkspace.tsx` | Tab navigation, worker info, turn card, evals, footer |
| `src/features/activity/components/ActivityStackTimeline.tsx` | Light/dark, pins, hints, kind legend |
| `src/features/activity/components/ActivityBar.tsx` | Kind color alignment, start markers |
| `src/components/cohorts/CohortListView.tsx` | Table columns, density, chevron |
| `src/components/cohorts/CohortDetailView.tsx` | Metric tiles, chart, action buttons |
| `src/components/common/StatusBadge.tsx` | Pill variants to match spec oklch values |
