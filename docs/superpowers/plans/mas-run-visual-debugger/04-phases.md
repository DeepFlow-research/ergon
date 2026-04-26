# 04 — Phases, Deliverables, Acceptance Gates

**Status:** draft.
**Scope:** delivery order for the frontend visual debugger branch. One PR is preferred if phases stay small; split after Phase C if review size gets uncomfortable.

Cross-refs: program in [`00-program.md`](00-program.md), frontend tasks in [`02-frontend-implementation.md`](02-frontend-implementation.md), test contract in [`03-tests-and-e2e.md`](03-tests-and-e2e.md).

---

## Delivery shape

Each phase should be a clean commit with:

- Scope: files touched.
- Deliverables: what now works.
- Acceptance gate: exact tests/commands before moving on.

Do not start the next phase while the current phase is red.

---

## Phase A — Plan and branch scaffold

**Scope**

- Create branch `feature/mas-run-visual-debugger-plan`.
- Add this plan folder.
- Keep mockups unmodified except as design reference.

**Deliverables**

- `docs/superpowers/plans/mas-run-visual-debugger/` exists.
- Branch records the implementation approach before app edits.

**Acceptance gate**

- `git branch --show-current` prints `feature/mas-run-visual-debugger-plan`.
- Plan docs are readable and self-contained.

---

## Phase B — Pure activity model

**Scope**

- `ergon-dashboard/tests/fixtures/mas-runs/concurrent-mas-run.json`
- `ergon-dashboard/src/features/activity/types.ts`
- `ergon-dashboard/src/features/activity/buildRunActivities.ts`
- `ergon-dashboard/src/features/activity/stackLayout.ts`
- Unit tests for both modules.
- Golden fixture semantic tests from [`06-fast-feedback-and-visual-review.md`](06-fast-feedback-and-visual-review.md).

**Deliverables**

- Activity derivation from `WorkflowRunState`, `RunEvent[]`, and `GraphMutationDto[]`.
- Deterministic overlap stack layout.
- Realistic MAS fixture replay proves concurrency is derived from overlap, not agent lanes.
- No React component changes yet.

**Acceptance gate**

- `pnpm --dir ergon-dashboard test src/features/activity`
- Golden fixture tests pass locally.
- `pnpm --dir ergon-dashboard run check`

**Not in this phase**

- No UI replacement.
- No backend DTO changes.

---

## Phase C — Bottom activity stack UI

**Scope**

- `ActivityStackTimeline.tsx`
- `ActivityBar.tsx`
- Wire into `RunWorkspacePage.tsx` behind existing timeline/live mode controls.
- Keep old `MutationTimeline` available until this phase is green.

**Deliverables**

- Bottom dock renders activity rows and bars.
- Sequence controls still work.
- Activity click selects task/sequence.
- Empty states are clear.

**Acceptance gate**

- `pnpm --dir ergon-dashboard run check`
- Local dashboard fixture page renders without runtime errors.
- Manual browser check against seeded run: graph visible, activity stack visible, workspace opens from activity.

**Not in this phase**

- No graph layout tuning unless the new dock breaks existing graph rendering.
- No smoke e2e assertions yet.

---

## Phase D — Time-aware workspace and graph highlights

**Scope**

- `TaskWorkspace.tsx` filters task evidence by selected timeline time.
- `DAGCanvas.tsx`/node components accept selected and highlighted task IDs.
- Preserve whole graph at selected `T`.

**Deliverables**

- Selecting an activity highlights graph task and opens workspace.
- Selecting a graph node highlights related activity bars.
- Workspace indicates timeline time/sequence.
- Evidence that did not exist at selected time is hidden in timeline mode.

**Acceptance gate**

- `pnpm --dir ergon-dashboard run check`
- Component/unit tests for time filtering pass.
- Manual check: scrub backward before a resource appears; workspace no longer shows that resource.

**Not in this phase**

- No persisted UI preferences.
- No virtualization.

---

## Phase E — Dashboard fixture e2e

**Scope**

- Add concurrent MAS dashboard fixture in `tests/helpers/dashboardFixtures.ts`.
- Add `tests/e2e/activity-stack.spec.ts`.
- Add selectors/ARIA labels required by [`03-tests-and-e2e.md §7`](03-tests-and-e2e.md).
- Add coarse browser geometry checks for graph node overlap.

**Deliverables**

- Fast deterministic Playwright test proves the visual debugger contract without real backend execution.
- Screenshot artifact captures the accepted layout shape when `VISUAL_DEBUGGER_SCREENSHOTS=1` is set locally.
- Browser geometry check catches catastrophic overlapping graph boxes without pixel-perfect assertions.
- Local-only PNG dump path works behind `VISUAL_DEBUGGER_SCREENSHOTS=1`.

**Acceptance gate**

- `pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts`
- Coarse graph overlap check passes.
- `VISUAL_DEBUGGER_SCREENSHOTS=1 pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts --project=chromium` writes PNGs under `ergon-dashboard/tmp/visual-debugger/`.
- Local PNG review command shows at least two activity rows and full graph canvas.

**Not in this phase**

- No backend harness DTO additions unless the fixture spec cannot cover a critical contract.

---

## Phase F — Canonical smoke e2e hardening

**Scope**

- Update `tests/e2e/_shared/smoke.ts`.
- Extend screenshot capture points.
- Optionally extend `BackendRunState` and backend harness DTO with `activity_event_count`, `activity_span_count`, `max_concurrency`.

**Deliverables**

- Real smoke run opens the new visual debugger.
- Playwright proves graph, activity stack, sequence controls, and workspace are usable.
- Screenshots are useful for PR review.
- No CI visual-diff gate is introduced.

**Acceptance gate**

- Local smoke Playwright spec green for at least one benchmark.
- Full e2e matrix remains green before merge.
- Smoke screenshot artifacts are generated as review aids only.
- If harness DTO fields are added, backend unit/integration harness tests pass.

**Not in this phase**

- No production DTO expansion unless a user-facing timestamp gap is proven.

---

## Phase G — Cleanup and docs

**Scope**

- Delete or rename obsolete `MutationTimeline.tsx`.
- Update dashboard architecture docs if they describe the old event stream/timeline split.
- Add a short note in PR description linking to the accepted mockup and this plan folder.

**Deliverables**

- No dead imports/components.
- Standing docs match the shipped dashboard behavior.

**Acceptance gate**

- `pnpm --dir ergon-dashboard run check`
- `rg -n "MutationTimeline" ergon-dashboard/src` returns either no matches or only the intentional renamed/reused sequence-control component.
- Final Playwright screenshots attached to PR.
- Final implementation review presents local PNGs for all new UI panels: full debugger page, graph canvas, activity stack bottom dock, and workspace drawer open on a selected task.

---

## Phase size estimates

| Phase | Scope | Est. diff size |
|---|---|---|
| A | Plan folder | ~500 lines docs |
| B | Activity pure model + golden fixture tests | ~650 LoC |
| C | Activity UI + RunWorkspace wiring + local PNG dump | ~750 LoC |
| D | Workspace filtering + graph highlights | ~300 LoC |
| E | Fixture e2e + browser geometry checks | ~350 LoC |
| F | Smoke hardening + optional harness DTO | ~200-500 LoC |
| G | Cleanup/docs | ~100 LoC |

---

## Failure modes

- **Activity bars look like lanes:** remove any row grouping by actor/agent. Rows are only collision rows.
- **Graph disappears while scrubbing:** inspect `replayToSequence` input state and current sequence; do not filter by selected task.
- **Workspace shows future evidence:** compare evidence timestamps to selected mutation `created_at`.
- **PNG review reveals cramped layout:** tune spacing/styling, then keep semantic and geometry tests green. Do not add pixel-perfect screenshot diffs in the first PR.
- **E2E flakes on exact counts:** assert minimum visibility and backend DTO truth, not pixel geometry.
- **Backend DTO temptation:** use the decision tree in `01-contracts-and-state.md`; most first-pass needs are frontend-derived.
