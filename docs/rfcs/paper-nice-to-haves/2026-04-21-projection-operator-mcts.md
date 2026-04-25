---
status: active
opened: 2026-04-21
author: paper-parity
architecture_refs: [docs/architecture/08_rl_loop.md, docs/architecture/04_persistence.md]
supersedes: []
superseded_by: null
paper_blocking: true
paper_blocking_reason: >-
  Preservation claim in Appendix~C (Table~\ref{tab:preservation}) makes
  two load-bearing MCTS commitments: (a) π_mcts preserves MCTS-entropy
  structure (diagonal ✓), and (b) π_json-log × MCTS-ent is ✓ (the raw
  substrate already captures everything an MCTS workload records). Both
  cells assume the mcts.* annotation namespace from this RFC's Option A
  is live by submission. Charlie commits to landing this RFC before the
  NeurIPS 2026 paper submission goes live.
---

# RFC: Projection operator — MCTS search-tree records

> **Paper-blocking.** This RFC is a hard pre-submission dependency for the
> NeurIPS 2026 Ergon paper, and carries **two** distinct load-bearing
> claims in Appendix~C's Table~\ref{tab:preservation}:
>
> 1. The diagonal ✓ under the *MCTS-ent* column in the $\pi_{\text{mcts}}$
>    row — requires the projection function in this RFC to exist in code.
> 2. The ✓ under the *MCTS-ent* column in the $\pi_{\text{json-log}}$
>    row — requires the `mcts.*` annotation namespace (Option A) to be
>    reserved and in the substrate, even if no MCTS driver has yet been
>    written. The claim is that Ergon's raw substrate *can* carry these
>    statistics without schema change; landing Option A as a reserved
>    namespace (with the default-filled projection behaviour) makes that
>    claim true by construction.
>
> The surrounding RFC text remains written in scoping voice, and the
> "Open questions" about whether a concrete MCTS driver ships alongside
> are *still* open (a driver is not paper-blocking; the namespace and
> projection are). Target: Option A landed — namespace reserved,
> projection function shipped with default-filled behaviour on
> zero-annotation trees, tests passing — before paper submission.

## Problem

The paper claims the Ergon substrate can emit a fifth trajectory
projection — **MCTS-style search-tree records** — suitable for training
tree-search policies (AlphaZero-style value/prior networks, ToT-fine-tune,
rStar-Math, OmegaPRM).

The shape consumers expect is a per-node record with:

- visit count `N(s, a)`;
- accumulated reward / Q-value `Q(s, a)`;
- prior probability `P(s, a)` (from the policy network at expansion time);
- parent / child pointers;
- terminal flag and backup-propagated value.

None of this exists in the Ergon schema today. `RunGraphMutation` is an
append-only audit log, not a search-statistics store. `RunGraphNode`
represents a subtask, not a search-tree node. There is no notion of
"visit count" or "backup" anywhere in the codebase.

Unlike the option-tagged and call-tree projections (sibling RFCs), the
MCTS projection **cannot be implemented as a pure read over the existing
schema** — the required statistics are never recorded.

## Proposal

Two options; this RFC recommends Option A.

### Option A (recommended): annotation-namespace for search statistics

Use the existing `RunGraphAnnotation` table (see
`ergon_core/core/persistence/graph/models.py:L123-L165`) with a reserved
namespace `mcts.*` to record per-node search statistics. Annotations are
already append-only and per-node-keyed, so this is zero schema change.

Namespace conventions:

```
mcts.visits       → {"n": int}
mcts.q_value      → {"q": float, "samples": int}
mcts.prior        → {"p": float, "model": str}
mcts.terminal     → {"terminal": bool, "value": float | null}
```

One annotation per `node.added` for `mcts.prior` (set by the expanding
policy). One annotation per backup for `mcts.visits` and `mcts.q_value`
(incremented by the MCTS driver).

The projection walks `RunGraphNode` + their `mcts.*` annotations and
emits a flat list of search-tree records:

```python
# ergon_core/core/rl/projections/mcts.py  (new)

from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class SearchTreeRecord:
    node_id: UUID
    parent_node_id: UUID | None
    state_token_ids: list[int]   # prompt_ids at expansion
    action_token_ids: list[int]  # completion_ids chosen
    visits: int
    q_value: float
    prior: float
    terminal: bool
    backup_value: float | None

def project_mcts(*, run_id: UUID) -> list[SearchTreeRecord]:
    ...
```

### Option B: dedicated `SearchTreeNode` table

Add a new table `search_tree_nodes` with the statistics columns inline.
Faster lookups; stricter typing; but requires an Alembic migration, a
write path in the MCTS driver, and a new invariant about consistency
between `RunGraphNode` and `SearchTreeNode`.

**Why Option A:** annotations are append-only like the rest of the WAL,
so they inherit replay / resumption semantics for free. The read-side
cost is one JOIN; acceptable until an MCTS-heavy workload emerges.
Option B is a follow-on if Option A becomes a bottleneck.

### MCTS-driver-side contract

A minimal MCTS driver (not in scope of this RFC) must:

1. At expansion time, write `mcts.prior` annotations for each child.
2. At rollout completion, backup values and write updated `mcts.visits`
   / `mcts.q_value` annotations up the tree.
3. At terminal states, write `mcts.terminal`.

The substrate does not enforce this; the driver is responsible. The
projection tolerates missing annotations (defaults: visits=0, q=0.0,
prior=uniform) so partially-annotated trees still project.

## Invariants affected

Adds an invariant to `docs/architecture/08_rl_loop.md`:

> **Invariant (MCTS search-tree projection).** Search statistics are
> stored in the `mcts.*` `RunGraphAnnotation` namespace. The projection
> defaults to visits=0, q=0.0, prior=uniform-over-siblings when
> annotations are missing, so a partially-annotated tree still projects
> without error.

Does not change any existing invariant. Reserves the `mcts.*` annotation
namespace — a new sub-invariant of the existing annotation tombstone
semantics.

## Migration

- New file `ergon_core/core/rl/projections/mcts.py`.
- No DB migration (Option A). A new Alembic revision if Option B is
  ultimately chosen.
- Tests: add `tests/rl/test_projection_mcts.py` with (a) fully-annotated
  tree, (b) partially-annotated tree (defaults filled), (c) zero-
  annotation tree (degenerate case — flat list of records with
  visits=0 / q=0.0 / prior=1/n).
- Reserve `mcts.*` namespace in a comment at
  `ergon_core/core/persistence/graph/models.py` near the annotation
  model.

## Alternatives considered

- **Option B: dedicated `SearchTreeNode` table** (discussed above). Deferred.
- **Reuse `GenerationTurn.metadata` JSON field for search stats.**
  Rejected: `GenerationTurn` is per-turn, not per-node. Search-tree
  statistics are per-node and evolve with backups — the annotations table
  is the right venue.
- **Skip this projection entirely and remove it from the paper.**
  Rejected by authors; tree-search RL is an increasingly active research
  thread and Ergon's append-only WAL is genuinely well-suited to it.

## Open questions

- Does any current workload actually *need* MCTS today, or is this
  purely a roadmap item? Resolved by the paper-blocking decision above:
  a concrete MCTS driver is **not** paper-blocking (it remains a roadmap
  item listed in Appendix~E), but the `mcts.*` namespace reservation and
  the default-filled projection function **are**. Accept Option A,
  ship the projection with tests, defer the first concrete driver PR
  to a follow-on RFC.
- Should `mcts.prior` be stored as a single annotation per parent (with
  all children's priors as one payload), or one per child? Lean per
  child for symmetry with visits / q_value.
- Does the projection need to reconstruct a DAG or only a tree? MCTS
  search-trees are trees by construction, but if a position is reached
  via multiple paths (transposition tables), the structure becomes a
  DAG. Suggest: tree only for v1; DAG support is a follow-on RFC.

## Paper parity

**Paper-blocking (two claims).** Sibling paper-blocking RFCs:
`2026-04-21-projection-operator-option-tagged.md`,
`2026-04-21-projection-operator-call-tree.md`. Unlike those, this RFC
is load-bearing for **two** cells in Appendix~C's
Table~\ref{tab:preservation}: the diagonal $\pi_{\text{mcts}}$ ×
*MCTS-ent* = ✓, and the raw-substrate-alias $\pi_{\text{json-log}}$ ×
*MCTS-ent* = ✓. The second claim is the reason the `mcts.*` annotation
namespace (Option A) must be reserved in the substrate before submission
even if no MCTS driver exists yet — the paper's position is that raw
$\tau_E$ dominates the preservation poset, which requires the substrate
to *be capable of* recording MCTS statistics without schema change.
Until landed, Appendix~E still describes the MCTS row as
`planned (RFC-2026-04-21-projection-operator-mcts)`; landing Option A
flips that row to `integrated` and satisfies both Appendix~C claims.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Add the `mcts.*` annotation-namespace reservation to
    `docs/architecture/08_rl_loop.md`.
  - Update Appendix E (paper repo) to cite accepted state.
  - Open a follow-on RFC for the first MCTS driver implementation
    (alpha-zero-style, ToT-style, or rStar-Math-style — pick one).
