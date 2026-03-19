# Frontend Spec Index

This folder defines the intended product behavior for the Arcane frontend before implementation and test work.

It exists so browser tests do not accidentally become the product spec.

The intended flow is:

1. specify frontend behavior here
2. derive the browser test plan from these docs
3. write seeded-state and controlled-event tests first
4. make the frontend pass them in red-green style
5. keep live browser probes tiny and explicit

## Documents

### `01_PRODUCT_OVERVIEW.md`

Defines what the frontend is for, who it is for, and what core user outcomes it must support.

### `02_INFORMATION_ARCHITECTURE.md`

Defines screens, routes, navigation, and the main data boundaries between runs, tasks, actions, outputs, and evaluation.

### `03_CORE_UX_LOOPS.md`

Defines the main user journeys the UI must support well.

### `04_RUNS_LIST_AND_RUN_DETAIL.md`

Defines the expected behavior of the runs list and run-level detail experience.

### `05_TASK_GRAPH_AND_TASK_DETAIL.md`

Defines graph identity, node interaction, task detail behavior, and graph/detail synchronization.

### `06_LIVE_UPDATES_AND_EVENT_MODEL.md`

Defines the intended snapshot-plus-live-update model for dashboard behavior.

### `07_FAILURE_STATES_AND_VISUAL_SYSTEM.md`

Defines error states, empty states, loading states, and the styling semantics that communicate meaning to users.

### `08_BROWSER_TEST_PLAN.md`

Maps the frontend behavior spec into a compact, high-signal browser test plan.

### `09_IMPLEMENTATION_ORDER.md`

Defines the intended red-green order for implementing and debugging the frontend.

### `10_GRAPH_VIEW_ANATOMY.md`

Defines the graph view as a concrete product surface: layout, node semantics, edge semantics, live-update behavior, and interaction rules.

### `11_WORKSPACE_VIEW_ANATOMY.md`

Defines the workspace view as a concrete product surface: header, evidence sections, chronology, communication, outputs, and evaluation behavior.

### `12_STATE_TO_UI_MAPPING.md`

Maps backend entities and live update families onto concrete UI surfaces so the frontend reflects persisted truth rather than inventing parallel state models.

### `13_COHORT_VIEW.md`

Defines the experiment cohort view as the top-level operations surface for monitoring many runs, cohort metadata, and aggregate progress.

## Relationship To The Test Docs

This folder should drive:

- `paper_code_structure_plans/bulletproof_test_setup/06_browser_and_dashboard_tests.md`

The relationship should be:

- frontend spec says what the UI must do
- browser test spec says how we prove it
- implementation order says how we go red-green
