---
status: open
opened: 2026-04-22
fixed_pr: null
priority: P2
invariant_violated: null
related_rfc: docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md
---

# Bug: `edge.added` mutation falls through to `unhandledMutations`

## Symptom

The contract test
[`graphMutations.test.ts:113`](ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts:113)
iterates `MutationTypeSchema.options` and asserts each mutation type has a
handler case that prevents it from being appended to `state.unhandledMutations`.
The assertion fails for `mutation_type: "edge.added"`:

```
mutation_type 'edge.added' is handled (does not fall through to unhandledMutations)
  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  true !== false
```

Every other `MutationType` variant (`node.added`, `node.removed`,
`node.status_changed`, `node.field_changed`, `edge.removed`,
`edge.status_changed`, `annotation.set`, `annotation.deleted`) passes this
contract test.

## Repro

```bash
pnpm -C ergon-dashboard run test -- --test-name-pattern="edge.added"
```

Or run the full contract suite via `pnpm run check:fe` — the failing case is
in `src/features/graph/contracts/graphMutations.test.ts` at line 113.

The synthetic mutation the test sends is built at
[`graphMutations.test.ts:74`](ergon-dashboard/src/features/graph/contracts/graphMutations.test.ts:74):

```ts
"edge.added": {
  mutation_type: "edge.added",
  source_node_id: nodeId,            // 00000000-...-0001 (== rootTaskId)
  target_node_id: "00000000-...-0002",
  status: "pending",
},
```

Applied against `emptyState()` (no tasks, empty `edges` map), the reducer
routes this into `unhandledMutations` instead of the `edge.added` arm.

## Root cause

Unknown — investigation needed. The reducer appears to have an `edge.added`
case arm already (grep shows a block around line 74 of the reducer source),
so the issue is not a missing arm. Likely candidates to check:

  - The arm runs but returns early (e.g. requires both source and target
    nodes to exist in `state.tasks`, which they don't in the synthetic
    `emptyState`) and then the outer switch's default pushes onto
    `unhandledMutations` anyway.
  - The arm's guard rejects the mutation because `target_node_id` points at
    an unknown node and the reducer treats "unknown target" as unhandled
    rather than as a buffered/pending edge.
  - The `new_value` shape in the test doesn't match what the reducer's
    runtime schema narrowing expects for the `edge.added` branch, so the
    switch falls through.

Confirm by reading `applyGraphMutation` in
`ergon-dashboard/src/features/graph/state/graphMutationReducer.ts` and tracing
what happens for an `edge.added` whose endpoints aren't in `state.tasks`.

## Scope

  - Blocks `pnpm run check:fe` (CI gate for the dashboard).
  - Violates the contract established by
    [`2026-04-18-dashboard-event-wiring-enforcement.md`](docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md):
    every `MutationType` must have a matching reducer arm. If `edge.added`
    truly isn't handled for edges whose endpoints arrive later, runs where
    edge events precede node events will silently drop edges.
  - Affects any dashboard consumer of the live event stream, not just tests
    — if the reducer really is dropping `edge.added` onto `unhandledMutations`
    in production, edges won't render until (or unless) a retry/backfill path
    replays the mutation.

## Proposed fix

Two sub-cases depending on root cause:

  1. **Reducer bug**: the arm exists but exits without returning the mutated
     state; fix is to ensure every `edge.added` returns through the arm (not
     the default). In-place fix in `graphMutationReducer.ts`.
  2. **Semantic gap**: the reducer legitimately rejects `edge.added` when
     endpoints are missing. Fix is either (a) relax the guard and buffer the
     edge, applying it on the node-added that satisfies it, or (b) update the
     contract test's `emptyState` to pre-seed the two node endpoints before
     dispatching `edge.added`, and document the ordering requirement in the
     reducer.

Pick after root-cause investigation. If the answer is "buffer edges", this
may deserve promotion to an RFC because it changes the reducer's invariant.

## On fix

When moving to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>`.
  - Confirm the full `MutationTypeSchema.options` loop passes in
    `graphMutations.test.ts`.
  - If the fix changed the reducer's contract (e.g. added buffering),
    update `docs/architecture/` to describe the new invariant and link it
    from `invariant_violated` above.
