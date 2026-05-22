# PR 15 Dashboard Event Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align live dashboard event payloads, generated frontend contracts, handwritten parsers, and run-state reducers after the PR 11/12 runtime vocabulary changes.

**Architecture:** Backend dashboard event contracts are the source of truth. Every backend live event must have a generated frontend contract. Handwritten parser logic may normalize transport details, but it must be tested against generated schemas and final `task_id` vocabulary. REST hydration adapters may remain separate, but live events must not bypass canonical conversion for graph mutations or context events.

**Tech Stack:** Python, Pydantic, TypeScript, Zod, Next.js dashboard tests, pytest, pnpm.

---

## PR 11 Head Update

PR 11 commit `a613875` added compatibility parsing for two live-event drift
cases: backend-wrapped graph mutation events and backend context-part payloads.
This PR should not redo that short-term patch. It should turn those shims into
canonical generated contracts and final field names.

## Scope

This PR should follow PR 12 because it depends on final `task_id` naming. It can
run in parallel with PR 13/14 if the backend event contract files are stable.
It is limited to contracts, reducers, fixtures, and tests; it should not include
visual dashboard component redesign.

## Primary Files

- Modify: `ergon_core/ergon_core/core/infrastructure/dashboard/event_contracts.py`
- Modify: `ergon_core/tests/unit/runtime/test_graph_mutation_contracts.py`
- Modify: `ergon_core/tests/unit/runtime/test_context_event_contracts.py`
- Modify: `ergon_core/tests/unit/dashboard/test_event_contract_types.py`
- Modify: `ergon-dashboard/scripts/generate-event-contracts.mjs`
- Modify: `ergon-dashboard/src/generated/events/*`
- Modify: `ergon-dashboard/src/lib/contracts/events.ts`
- Modify: `ergon-dashboard/src/lib/contracts/contextEvents.ts`
- Modify: `ergon-dashboard/src/lib/runEvents.ts`
- Modify: `ergon-dashboard/src/lib/run-state/reducers.ts`
- Modify: `ergon-dashboard/tests/contracts/contracts.test.ts`
- Modify: `ergon-dashboard/tests/contracts/context-events.contract.test.ts`
- Modify: `ergon-dashboard/tests/contracts/run-state-roundtrip.contract.test.ts`

## Code TODOs / Comments To Remove

When PR 15 lands, remove the dashboard parser TODOs and compatibility comments
that the generated contracts replace. Expected cleanup targets include:

- `ergon-dashboard/src/lib/contracts/events.ts`: remove `TODO(E2b)` comments
  for generated evaluation, thread/message, context, and workflow-started event
  schemas once every backend live event has a generated frontend contract.
- `ergon-dashboard/src/features/graph/contracts/graphMutations.*` and reducer
  tests: remove comments and fixtures that normalize backend
  `source_task_id`/`target_task_id` into deleted `source_node_id`/
  `target_node_id` names.
- `ergon-dashboard/tests/helpers/testHarnessClient.ts` and
  `ergon-dashboard/tests/helpers/backendHarnessClient.ts`: replace
  `parent_node_id` fixture/helper vocabulary with `parent_task_id` after PR 12.
- Backend/dashboard contract tests: delete temporary comments that describe
  backend-wrapped graph mutations or backend context-part payloads as
  compatibility shims once those shapes are canonical generated contracts.
- Any e2e assertion comments that explain a "node_id join" should be removed or
  rewritten to the final task-id contract.

## Tasks

### Task 1: Snapshot Backend Event Shapes

- [ ] Add backend tests that serialize representative graph mutation, context event, workflow started, task status, evaluation, sandbox, and resource events.
- [ ] Assert graph edge payloads use `source_task_id` and `target_task_id`.
- [ ] Assert context events use the canonical context payload shape emitted by backend runtime.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema
uv run pytest ergon_core/tests/unit/runtime/test_graph_mutation_contracts.py ergon_core/tests/unit/runtime/test_context_event_contracts.py ergon_core/tests/unit/dashboard/test_event_contract_types.py -q
```

Expected before implementation: fail where tests expose current backend/frontend drift.

### Task 2: Generate Missing Event Contracts

- [ ] Extend backend event contract export so graph mutation and context events are first-class generated frontend contracts.
- [ ] Update `ergon-dashboard/scripts/generate-event-contracts.mjs` only if the generator cannot consume the backend schema as-is.
- [ ] Regenerate frontend event files.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema/ergon-dashboard
pnpm run generate:contracts:events
```

Expected after implementation: generated files include graph mutation and context event contracts, or the equivalent canonical event union.

### Task 3: Replace Compatibility Shims With Canonical Contracts

- [ ] Keep the PR 11 behavior that accepts nested backend `{ mutation: ... }` graph events, but move the accepted shape into generated/frontend canonical contracts.
- [ ] Remove the long-term need for `source_node_id` / `target_node_id` compatibility by making frontend graph contracts and reducers consume `source_task_id` / `target_task_id`.
- [ ] Keep the PR 11 behavior that accepts backend context-part payloads, but move normalization into a shared canonical converter or generated contract path used by both REST hydration and live events.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema/ergon-dashboard
pnpm test -- tests/contracts/contracts.test.ts tests/contracts/context-events.contract.test.ts
```

Expected after implementation: live parser contract tests pass with backend-shaped fixtures without relying on stale node-id field names.

### Task 4: Align Workflow Started Task Tree

- [ ] Update backend or frontend contract expectations so `workflow.started` task-tree nodes agree on required `status`, `level`, and resource-id fields.
- [ ] Do not invent frontend-only fields in the contract layer; derive UI fields inside run-state selectors or reducers.
- [ ] Run:

```bash
pnpm test -- tests/contracts/run-state-roundtrip.contract.test.ts
```

Expected after implementation: a backend workflow-started fixture round-trips through frontend run-state without manual patching.

### Task 5: Update Reducers And Fixtures

- [ ] Update run-state reducers to consume canonical graph/context events.
- [ ] Update dashboard fixtures and e2e harness client DTOs from `parent_node_id` to `parent_task_id` if PR 12 removed public node vocabulary.
- [ ] Run:

```bash
pnpm test -- src/lib/run-state/reducers.test.ts tests/contracts/run-state-roundtrip.contract.test.ts
pnpm test -- tests/e2e/live.smoke.spec.ts
```

Expected after implementation: live smoke and reducer tests consume canonical event payloads.

### Task 6: Add Drift Guards

- [ ] Add a test that fails when any backend dashboard event has no generated frontend contract.
- [ ] Add a test that fails when handwritten frontend parser fields diverge from generated event fields.
- [ ] Run:

```bash
pnpm test -- tests/contracts/contracts.test.ts
uv run pytest ergon_core/tests/unit/dashboard/test_event_contract_types.py -q
```

Expected after implementation: future backend event additions require corresponding frontend contract coverage.

## Acceptance Criteria

- Live dashboard graph events parse backend-emitted nested graph mutation payloads.
- Live context events share canonical parsing with REST hydration.
- Frontend contracts use `task_id` vocabulary consistently.
- Contract tests pass in Python and TypeScript.
- Dashboard e2e smoke can hydrate and update a run with live events.

## Do Not Include

- Visual redesign of dashboard components.
- Runtime schema migration work.
- Registry or evaluator cleanup.
