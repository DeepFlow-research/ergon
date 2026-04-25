---
status: active
opened: 2026-04-21
author: paper-parity
architecture_refs: [docs/architecture/08_rl_loop.md, docs/architecture/04_persistence.md]
supersedes: []
superseded_by: null
paper_blocking: true
paper_blocking_reason: >-
  Preservation claim in Appendix~C (Table~\ref{tab:preservation}) requires
  π_macro to be an implementable projection that preserves option-termination
  structure. Charlie commits to landing this RFC and its implementation
  before the NeurIPS 2026 paper submission goes live.
---

# RFC: Projection operator — option-tagged transitions

> **Paper-blocking.** This RFC is a hard pre-submission dependency for the
> NeurIPS 2026 Ergon paper. Appendix~C's preservation table claims
> $\pi_{\text{macro}}$ preserves option-termination structure (diagonal
> ✓ cell under the *Opt-term* column); that claim requires the projection
> function specified in this RFC to exist in code by submission time. The
> surrounding RFC text remains written in scoping voice, but the decision
> to ship has already been made — this is no longer a "nice to have."
> Target: implementation landed and tested before paper submission.

## Problem

The paper (§3.2 and Appendix E) lists five canonical trajectory projections
the Ergon substrate can emit. Two are implemented today (step-indexed
tuples, per-agent streams — both via `extract_agent_trajectories` at
`ergon_core/core/rl/extraction.py:L49-L117`). Three are not. This RFC
covers the **option-tagged transitions** projection (hierarchical /
semi-MDP framing).

The projection's purpose is to feed hierarchical RL trainers (option-critic,
HIRO, FuN-style) that consume `(s, option, sub-policy-rewards, s')` tuples
rather than flat `(s, a, r, s')`. The substrate already records every input
the projection needs:

- `RunGraphNode` (parent_node_id) at
  `ergon_core/core/persistence/graph/models.py:L44-L89` — the call-tree
  needed to identify option boundaries.
- `RunGraphMutation` events at
  `ergon_core/core/persistence/graph/models.py:L172-L186` — give a totally
  ordered timeline of `node.added` / `node.status_changed` events.
- `GenerationTurn` rows at
  `ergon_core/core/persistence/telemetry/models.py:L383-L464` — provide the
  `(prompt_ids, completion_ids, logprobs)` that bind to each option.

But there is no projection function. `extract_agent_trajectories` flattens
the call tree into per-agent token streams; option boundaries are
discarded.

## Proposal

Add a new projection in `ergon_core/core/rl/projections/option_tagged.py`
(new package). API:

```python
# ergon_core/core/rl/projections/option_tagged.py  (new)

from dataclasses import dataclass
from ergon_core.core.persistence.graph.models import RunGraphNode

@dataclass(frozen=True)
class OptionBoundary:
    option_id: str          # parent_node_id whose lifetime defines this option
    sub_policy_id: str      # the worker / agent that executes inside
    enter_sequence: int     # mutation sequence at node.added
    exit_sequence: int      # mutation sequence at terminal status
    return_value: float     # accumulated reward inside the option

@dataclass(frozen=True)
class OptionTaggedTransition:
    s: list[int]            # prompt_ids at option entry
    option: str             # option_id
    rewards: list[float]    # per-step rewards inside this option
    s_prime: list[int]      # prompt_ids at option exit (next-state)

def project_option_tagged(*, run_id: UUID) -> list[OptionTaggedTransition]:
    """Walk RunGraphMutation timeline; identify option boundaries via
    parent_node_id transitions; aggregate sub-policy rewards within each
    option. Returns one transition per option entry."""
    ...
```

The projection consumes the same `(MutationLog, GenerationTurns,
TaskEvaluations)` triple that `extract_agent_trajectories` consumes — no
new data sources required. The walk is O(N + M) in nodes + mutations.

### Option-boundary rule

An *option* is the lifetime of a `RunGraphNode` from `node.added` to its
first terminal `node.status_changed` (in `{COMPLETED, FAILED, CANCELLED}`).
Sub-policy rewards are the rewards assigned to `GenerationTurn` rows whose
`worker_binding_key` matches the option's executing worker.

This rule is consistent with the existing notion of a "task" in
`docs/architecture/02_runtime_lifecycle.md` and does not require any new
schema fields.

## Invariants affected

Adds an invariant to `docs/architecture/08_rl_loop.md`:

> **Invariant (option-tagged projection).** The option-tagged projection
> defines an option as the lifetime of a single `RunGraphNode` from
> `node.added` to first terminal `node.status_changed`. Hierarchical
> trainers consuming this projection get one transition per option entry.

No existing invariants change. The `RunGraphNode` parent/child structure,
already documented in `04_persistence.md`, is the load-bearing source of
truth.

## Migration

- New package `ergon_core/core/rl/projections/` with `__init__.py` and
  `option_tagged.py`. Empty `__init__.py` until additional projections
  land via the sibling RFCs.
- No DB migration. No API change to `/rollouts/{batch_id}` (this
  projection is consumed directly by trainer adapters that opt in).
- Tests: add `tests/rl/test_projection_option_tagged.py` with three
  cases — single-task run (one option), parent-with-two-children run
  (three options), and a deeper nested run (test the recursive case).

## Alternatives considered

- **Define an option as a sequence of `GenerationTurn` rows up to a
  tool-call boundary.** Rejected: tool calls are intra-option events, not
  option boundaries. The call-tree projection (separate RFC) covers the
  intra-option tool-call structure.
- **Defer until a hierarchical trainer is integrated and let the adapter
  invent its own boundary rule.** Rejected: would create two competing
  notions of "option" between, e.g., a future SkyRL hierarchical adapter
  and a future option-critic adapter. The boundary rule is substrate
  policy, not trainer policy.
- **Materialize options as a new DB table.** Rejected: derivable in O(N)
  from existing tables. Materialization is a caching choice that can
  follow if the projection becomes hot.

## Open questions

- Should `OptionBoundary` be exposed as a public API type or stay internal
  to the projection? Lean public (downstream tooling will want to inspect
  it), but only after a real consumer exists.
- How are nested options (option-within-option) represented in the
  flat list returned by `project_option_tagged`? Suggest: tag each
  transition with `parent_option: str | None` and let the consumer build
  the tree.

## Paper parity

**Paper-blocking.** This RFC is one of three paper-blocking projection
RFCs (siblings: `2026-04-21-projection-operator-call-tree.md`,
`2026-04-21-projection-operator-mcts.md`). Appendix~C of the NeurIPS
2026 paper claims a specific preservation pattern for $\pi_{\text{macro}}$
in Table~\ref{tab:preservation}; that claim is load-bearing for §2.2
("different communities record different things") and for the paper's
central thesis that Ergon's raw substrate $\tau_E$ uniquely dominates the
poset of community-native projections. The claim requires the projection
function specified here to exist in code by submission. Until landed,
Appendix~E still describes the option-tagged row as
`planned (RFC-2026-04-21-projection-operator-option-tagged)`; landing
flips that row to `integrated` and satisfies the Appendix~C claim.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Add the option-boundary invariant to `docs/architecture/08_rl_loop.md`.
  - Update Appendix E (paper repo) to cite accepted state.
  - Link the implementation plan in `docs/superpowers/plans/`.
