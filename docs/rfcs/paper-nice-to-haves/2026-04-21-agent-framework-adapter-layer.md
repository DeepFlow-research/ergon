---
status: active
opened: 2026-04-21
author: paper-parity
architecture_refs: [docs/architecture/02_runtime_lifecycle.md, docs/architecture/03_providers.md, docs/architecture/06_builtins.md#extension-points]
supersedes: []
superseded_by: null
paper_blocking: false
paper_blocking_reason: >-
  Not paper-blocking. The paper (Appendix E) honestly describes the five
  non-PydanticAI agent frameworks as `planned (RFC-...)` rows. Landing
  this RFC flips rows to `integrated`, but the paper's claims are
  well-formed under either state. The Appendix C preservation table does
  not depend on any of these adapters existing; it is about projection
  operators over already-recorded trajectories.
---

# RFC: Agent-framework adapter layer

> **Not paper-blocking.** Appendix~E of the NeurIPS 2026 Ergon paper
> lists the five non-PydanticAI agent frameworks (LangGraph, CrewAI,
> AutoGen, Google ADK, Claude Code) as `planned (RFC-...)` rows, and
> the paper is honest about which integrations are shipped today versus
> scoped-but-not-yet-written. This RFC may land before, during, or after
> paper submission without altering any paper claim. The preservation
> table in Appendix~C is about projections over recorded trajectories,
> not about which runtimes produce those trajectories; no cell in that
> table changes based on which adapters exist. Contrast with the three
> projection RFCs in this directory, which *are* paper-blocking.

## Problem

The paper (Appendix E, "Tech-Stack Integrations") describes Ergon as hosting
six agent frameworks as inner runtimes: Pydantic AI, LangGraph, CrewAI,
AutoGen, Google ADK, and Claude Code. The codebase today integrates **one**
of those six.

Concretely, the only adapter that wraps a third-party agent loop and emits
mutations into Ergon's `RunRecord` / `RunGraph` lives in
`ergon_builtins/ergon_builtins/workers/baselines/react_worker.py:L28-L105`,
which wraps `pydantic_ai.Agent.iter()`. The supporting machinery is:

- `ergon_core/ergon_core/core/persistence/context/assembly.py:L94-L130` —
  rebuilds `pydantic_ai.messages.ModelRequest` / `ModelResponse` from stored
  `RunContextEvent` rows so a worker can resume mid-trajectory.
- `ergon_core/ergon_core/core/providers/generation/pydantic_ai_format.py` —
  pulls text, tool calls, and logprobs out of serialized PydanticAI
  responses for downstream extraction.
- `ergon_builtins/ergon_builtins/tools/research_rubrics_toolkit.py:L63` —
  wraps Ergon-side tools as `pydantic_ai.tools.Tool` instances.

For LangGraph, CrewAI, AutoGen, Google ADK, and Claude Code, there are zero
imports, zero adapter files, and zero declared dependencies anywhere in
`ergon_core`, `ergon_builtins`, `ergon_infra`, or `tests`.

The PydanticAI integration emerged organically — there is no documented
adapter contract, no abstract base class, and no test that asserts "this
is what an agent-framework adapter must do". The pattern is implicit, lives
in one place, and has not been generalized. Adding a second framework today
means duplicating undocumented assumptions about message replay, tool
serialization, logprob extraction, and mutation emission.

## Proposal

Promote the implicit Pydantic AI integration to an explicit
**`AgentRuntimeAdapter`** contract that any inner-loop framework can
implement. Then ship a stub adapter per planned framework that demonstrates
the shape but defers full integration to follow-on RFCs.

### Contract sketch

```python
# ergon_core/ergon_core/api/agent_runtime_adapter.py  (new)

from typing import Protocol
from ergon_core.api.run_context import RunContextEvent
from ergon_core.api.tool import ToolDescriptor

class AgentRuntimeAdapter(Protocol):
    """Wraps a third-party agent loop so it can be driven by Ergon.

    Implementations MUST:
      - serialize each turn as a sequence of RunContextEvents
        (system_prompt | user_message | assistant_text | thinking |
         tool_call | tool_result) committed to the WAL before returning;
      - emit GenerationTurn rows with logprobs and env_mask when the
        underlying framework exposes them;
      - rebuild framework-native message state from stored events
        (i.e. support resumption from any sequence boundary);
      - expose Ergon-side tools as the framework's native tool type.
    """

    framework_id: str  # e.g. "pydantic_ai", "langgraph", "crewai"

    def run_turn(self, *, input_event: RunContextEvent,
                 tools: list[ToolDescriptor]) -> list[RunContextEvent]: ...

    def replay_to(self, *, events: list[RunContextEvent]) -> object:
        """Rebuild framework-native message state. Returns native object."""
        ...
```

Refactor `ReActWorker` to be the concrete `pydantic_ai`
`AgentRuntimeAdapter`. Add stub adapters in
`ergon_infra/ergon_infra/agent_adapters/` (new package) for each planned
framework: `langgraph_adapter.py`, `crewai_adapter.py`,
`autogen_adapter.py`, `google_adk_adapter.py`, `claude_code_adapter.py`.
Each stub raises `NotImplementedError` with a one-line pointer to the
follow-on RFC, but registers `framework_id` and a `requirements` block so
downstream tooling can discover what's planned.

### Per-framework follow-on RFCs

Each of the five planned adapters gets its own follow-on RFC after this
contract lands. The follow-on RFCs are not blocked on this one being
implemented — they can be written speculatively against the contract sketch
above. Suggested order (easiest to hardest):

1. **Claude Code** — agent loop is `claude-code-sdk`; trajectory shape is
   already close to Ergon's event log.
2. **LangGraph** — agent loop is the compiled `StateGraph`; tool calls map
   1:1; multi-node walks need a flattening rule onto Ergon's `RunGraphNode`
   parent_node_id.
3. **Google ADK** — analogous to LangGraph (state-machine-shaped).
4. **AutoGen** — multi-agent by default; needs a per-agent `worker_binding_key`
   convention.
5. **CrewAI** — task delegation is opaque; will likely require shimming
   into Ergon's existing `spawn_subtask` action.

## Invariants affected

This RFC introduces a new public-API invariant in
`docs/architecture/01_public_api.md`:

> **Invariant (agent runtime adapters).** Every framework integrated as an
> Ergon inner runtime ships an `AgentRuntimeAdapter` implementation that
> commits one `RunContextEvent` per turn-boundary observable to the
> framework, before returning control. Adapters that cannot meet this
> contract MUST NOT be merged.

Touches `docs/architecture/03_providers.md` (provider/adapter boundary) and
`docs/architecture/06_builtins.md#extension-points` (adds a new extension
point: "Add an agent runtime").

## Migration

- `ReActWorker` becomes the canonical example implementation. No behavior
  change to existing benchmarks; the class gains an explicit
  `framework_id = "pydantic_ai"` attribute and is documented as the
  reference adapter.
- Stub adapters in `ergon_infra/agent_adapters/` add 5 new files, no edits
  to existing call paths.
- No DB / Alembic migration. Schema is unchanged; this RFC formalizes
  what the schema already supports.
- Tests: add `tests/state/test_agent_adapter_contract.py` with one passing
  case (PydanticAI via ReActWorker) and five `pytest.skip` cases naming
  the follow-on RFCs.

## Alternatives considered

- **Leave the contract implicit.** Rejected: the paper claims six
  integrations and we have one. A new contributor adding LangGraph today
  has no reference; the result will be a second snowflake.
- **Adapt frameworks behind a single mega-class.** Rejected: each framework
  has different replay semantics; single-class polymorphism becomes a
  long if-elif on `framework_id`. The Protocol approach lets each adapter
  live in its own file.
- **Cut the planned adapters from the paper and only describe Pydantic
  AI.** Rejected by the paper authors — Appendix E is framed as a
  descriptive integrations *map*, including planned rows; this RFC is the
  parity work.

## Open questions

- Should `AgentRuntimeAdapter` be a `Protocol` (structural) or a
  `class(ABC)` (nominal)? `Protocol` is cheaper to adopt; `ABC` enforces
  presence at class-definition time (cf. the `Benchmark` ABC pattern in
  RFC `2026-04-18-onboarding-deps-on-benchmark-abc.md`). Lean toward
  `ABC` for consistency.
- The `replay_to(...)` return type is `object` because each framework
  returns its own native message-list type. Worth a `TypeVar` parametrization?
  Probably not — the adapter is the only consumer of its own return type.
- Where does the framework-id registry live? Suggest
  `ergon_infra/agent_adapters/registry.py` mapping `framework_id` →
  adapter class, mirroring the trainer-adapter registry proposed in
  RFC `2026-04-21-rl-trainer-adapter-expansion.md`.

## Paper parity

This RFC closes one of three parity gaps identified during the Appendix E
audit (sibling RFCs: `2026-04-21-rl-trainer-adapter-expansion.md`,
`2026-04-21-projection-operator-*.md`). Until this RFC is accepted and the
five follow-on adapters land, Appendix E describes those rows as
`planned (RFC-2026-04-21-agent-framework-adapter-layer)` rather than
`integrated`.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Add `AgentRuntimeAdapter` to `docs/architecture/01_public_api.md` core
    abstractions.
  - Add the new extension point ("Add an agent runtime") to
    `docs/architecture/06_builtins.md#extension-points`.
  - Open the five follow-on RFCs (one per planned framework).
  - Update Appendix E in the paper repo to reference accepted state.
