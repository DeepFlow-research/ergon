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
  π_call-tree to be an implementable projection that preserves call-depth
  structure. Charlie commits to landing this RFC and its implementation
  before the NeurIPS 2026 paper submission goes live.
---

# RFC: Projection operator — nested sub-LM call tree

> **Paper-blocking.** This RFC is a hard pre-submission dependency for the
> NeurIPS 2026 Ergon paper. Appendix~C's preservation table claims
> $\pi_{\text{call-tree}}$ preserves call-depth structure (diagonal ✓
> cell under the *Call-dep* column); that claim requires the projection
> function specified in this RFC to exist in code by submission time. In
> addition, the "spawn-ordering invariant" in the Proposal section is a
> substrate guarantee the paper implicitly relies on; the state-invariant
> test that confirms it must land alongside the projection. The
> surrounding RFC text remains written in scoping voice, but the decision
> to ship has already been made — this is no longer a "nice to have."
> Target: implementation landed and tested before paper submission.

## Problem

The paper claims the Ergon substrate emits a "nested sub-LM call tree"
projection: a recursive structure where each node is a turn (or a tool
invocation) and edges are parent → child sub-call relationships. This
projection feeds reward-model training pipelines that score reasoning
*structure* (not just final answers) and downstream visualization tooling
that renders rollouts as collapsible trees.

The substrate records all the inputs:

- `RunGraphNode.parent_node_id` at
  `ergon_core/core/persistence/graph/models.py:L44-L89` — sub-task
  containment.
- `RunContextEvent` at
  `ergon_core/core/persistence/context/models.py:L25-L49` — the per-turn
  events (`system_prompt`, `user_message`, `assistant_text`, `thinking`,
  `tool_call`, `tool_result`).
- `GenerationTurn` at
  `ergon_core/core/persistence/telemetry/models.py:L383-L464` — the
  generation metadata (model, logprobs, env_mask) bound to each
  assistant turn.

But `extract_agent_trajectories` flattens all of this into a single token
stream per agent. Tool calls are inlined as tokens; sub-task boundaries
are erased. There is no recursive tree builder.

## Proposal

Add a new projection in `ergon_core/core/rl/projections/call_tree.py`. It
walks the `(RunGraphNode, RunContextEvent)` pair to produce a tree:

```python
# ergon_core/core/rl/projections/call_tree.py  (new)

from dataclasses import dataclass, field
from uuid import UUID
from ergon_core.core.persistence.context.models import RunContextEventKind

@dataclass
class CallTreeTurn:
    """One assistant turn within a single agent's execution."""
    sequence: int
    role: str                       # "assistant" | "user" | "system"
    content: str | None             # text payload (assistant_text, etc.)
    thinking: str | None            # if event_kind == "thinking"
    tool_calls: list["ToolInvocation"] = field(default_factory=list)
    children: list["CallTreeTurn"] = field(default_factory=list)
    # children are non-empty when this turn spawned sub-tasks

@dataclass
class ToolInvocation:
    tool_name: str
    arguments: dict
    result: str | None              # populated by the matching tool_result
    spawned_node_id: UUID | None    # set if this tool call spawned a sub-task

@dataclass
class CallTree:
    run_id: UUID
    root_node_id: UUID
    turns: list[CallTreeTurn]       # the root node's turns; each turn's
                                    # children list points at sub-task subtrees

def project_call_tree(*, run_id: UUID) -> CallTree:
    """Recursively walk RunGraphNode by parent_node_id; for each node,
    fold its RunContextEvent stream into CallTreeTurn objects, then attach
    sub-task subtrees as children of the spawning turn."""
    ...
```

The recursion is depth-first on `parent_node_id`. Spawning is detected by
matching a `tool_call` event whose `tool_name == "spawn_subtask"` to the
`RunGraphNode` it created (the link is the `node.added` mutation that
follows the tool call within ε of its sequence number).

### Output formats

`CallTree` itself is the canonical in-memory representation. Two
serialization helpers ship with the projection:

- `to_jsonl(call_tree, fp)` — each line is one `CallTreeTurn` with a
  `path: list[int]` indexing its position in the tree. Suitable for
  `pandas.read_json(lines=True)`.
- `to_dict(call_tree) -> dict` — nested dict mirroring the in-memory
  shape. Suitable for direct ingestion into reward-model training
  pipelines that expect tree-shaped JSON (DPO-tree, RLAIF-tree, etc.).

## Invariants affected

Adds an invariant to `docs/architecture/08_rl_loop.md`:

> **Invariant (call-tree projection).** The call-tree projection
> reconstructs sub-task spawning by matching `tool_call(spawn_subtask)`
> events to `node.added` mutations within the same run, ordered by
> mutation sequence. The substrate guarantees these two events appear in
> immediate sequence (the spawning is synchronous within the worker's
> turn).

If this guarantee is *not* in fact provided by the existing runtime,
that is a substrate bug to fix before this projection ships — captured as
an open question below.

## Migration

- New file `ergon_core/core/rl/projections/call_tree.py`.
- No DB migration. No API change.
- Tests: add `tests/rl/test_projection_call_tree.py` with cases for
  (a) zero-spawn run (flat list of turns), (b) one-spawn run (tree of
  depth 2), (c) multi-spawn run (tree of depth 3+, sibling sub-tasks),
  (d) tool-call without spawn (no `children` populated, `tool_calls`
  populated).

## Alternatives considered

- **Fold call-tree information into `extract_agent_trajectories`**
  (return both flat and tree shape from one function). Rejected: the
  consumers are different (RL trainers want flat; reward models want
  tree); coupling them means every trainer pays the tree-walk cost.
- **Materialize the call tree in a new `RunCallTree` table.** Rejected:
  derivable in O(N + M) from existing tables; materialization is a
  caching choice deferrable until the projection becomes hot.
- **Use Mermaid/Graphviz emission as the canonical format.** Rejected:
  reward-model training pipelines want JSON; visualization tooling can
  render JSON via a thin adapter.

## Open questions

- Does the runtime in fact emit `tool_call(spawn_subtask)` immediately
  before its `node.added` mutation in mutation-sequence order? If not,
  the matching rule above breaks. Action item: add a `tests/state/`
  test verifying this invariant before this RFC's implementation lands.
- How do we handle a `tool_call` that *fails* before spawning the
  sub-task? Suggest: `spawned_node_id` stays `None`; the failure is
  recoverable from the tool_result's payload.
- Should `CallTreeTurn` carry `logprobs` for downstream scoring, or do
  we keep the projection token-shape-free and have consumers join
  back to `GenerationTurn`? Lean keep it token-free.

## Paper parity

**Paper-blocking.** Sibling paper-blocking RFCs:
`2026-04-21-projection-operator-option-tagged.md`,
`2026-04-21-projection-operator-mcts.md`. Appendix~C of the NeurIPS 2026
paper claims $\pi_{\text{call-tree}}$ preserves call-depth structure in
Table~\ref{tab:preservation}; that claim requires the projection function
specified here to exist in code by submission. It also depends on the
spawn-ordering invariant being confirmed (see "Open questions") —
resolving that open question is paper-blocking alongside the projection
implementation, because if the substrate doesn't in fact order spawns
synchronously with the originating turn, the projection is not
well-defined and Table~\ref{tab:preservation}'s ✓ would have to soften
to ~. Until landed, Appendix~E still describes the call-tree row as
`planned (RFC-2026-04-21-projection-operator-call-tree)`; landing flips
that row to `integrated` and satisfies the Appendix~C claim.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Add the spawn-ordering invariant to
    `docs/architecture/08_rl_loop.md` (and confirm or fix runtime).
  - Update Appendix E (paper repo) to cite accepted state.
