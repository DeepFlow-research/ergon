---
status: active
opened: 2026-04-21
author: paper-parity
architecture_refs: [docs/architecture/08_rl_loop.md]
supersedes: []
superseded_by: null
paper_blocking: false
paper_blocking_reason: >-
  Not paper-blocking. The paper (Appendix E) honestly describes the six
  non-shipped RL trainers as `planned (RFC-...)` rows. Landing this RFC
  flips rows to `integrated`, but the paper's claims are well-formed
  under either state. The Appendix C preservation table is about
  projection operators over already-recorded trajectories, not about
  downstream trainer consumption.
---

# RFC: RL trainer adapter expansion

> **Not paper-blocking.** Appendix~E of the NeurIPS 2026 Ergon paper
> lists the six non-shipped RL trainers (SkyRL, ProRL Agent, AReaL,
> AgentGym-RL, RAGEN, MARTI) as `planned (RFC-...)` rows, and the paper
> is honest about which adapters ship today versus which are scoped.
> This RFC may land before, during, or after paper submission without
> altering any paper claim. The preservation table in Appendix~C is
> about projections over recorded trajectories, not about downstream
> trainer consumption; no cell in that table changes based on how many
> trainers consume `/rollouts/{batch_id}`. Contrast with the three
> projection RFCs in this directory, which *are* paper-blocking.

## Problem

The paper (Appendix E) describes Ergon as feeding **nine** RL trainers via
thin HTTP adapters: TRL, VERL, OpenRLHF, SkyRL, ProRL Agent, AReaL,
AgentGym-RL, RAGEN, and MARTI. The codebase today ships **three**:

- `ergon_infra/ergon_infra/adapters/trl_http.py` (L1-L92) — TRL GRPO
- `ergon_infra/ergon_infra/adapters/verl_http.py` (L1-L83) — VERL agent loop
  (via `@register("ergon")`)
- `ergon_infra/ergon_infra/adapters/openrlhf_http.py` (L1-L85) — OpenRLHF
  agent-func pattern

All three follow the same handshake (documented in
`docs/architecture/08_rl_loop.md:L132-L135`):

1. `POST /rollouts/submit` with `{"definition_id": UUID, "num_episodes": int}`
   → `{"batch_id": UUID}` (HTTP 202).
2. Poll `GET /rollouts/{batch_id}` until `status in {"complete", "failed"}`.
3. Receive `{"status": "complete", "trajectories": [Trajectory, ...]}`.
4. Map each `Trajectory` into the trainer's native batch type.

For SkyRL, ProRL Agent, AReaL, AgentGym-RL, RAGEN, and MARTI there are
zero adapter files, zero imports, and zero `pyproject.toml` optional-deps
entries. There is no `TrainerBackend` enum, registry, or factory — each
adapter is discovered today by "grep for `*_http.py` in
`ergon_infra/adapters/`".

The server side (`ergon_core/core/api/rollouts.py`,
`ergon_core/core/rl/rollout_service.py`,
`ergon_core/core/rl/extraction.py`) is trainer-agnostic. The gap is
entirely on the adapter-side: six missing files.

## Proposal

Two things, sequenced as two PRs.

### Part 1 — formalize the contract

Elevate the handshake from documentation prose to a public
`TrainerHttpAdapter` Protocol in `ergon_infra/ergon_infra/adapters/base.py`
(new file) and add a `TrainerBackend` enum mapping each supported backend
to its adapter module. Shape:

```python
# ergon_infra/ergon_infra/adapters/base.py  (new)

from enum import Enum
from typing import Protocol
from ergon_core.core.rl.rollout_types import Trajectory

class TrainerBackend(str, Enum):
    TRL          = "trl"
    VERL         = "verl"
    OPENRLHF     = "openrlhf"
    SKYRL        = "skyrl"           # planned
    PRORL_AGENT  = "prorl_agent"     # planned
    AREAL        = "areal"           # planned
    AGENTGYM_RL  = "agentgym_rl"     # planned
    RAGEN        = "ragen"           # planned
    MARTI        = "marti"           # planned

class TrainerHttpAdapter(Protocol):
    backend: TrainerBackend
    def submit(self, *, definition_id: str, num_episodes: int) -> str:
        """POST /rollouts/submit; returns batch_id."""
        ...
    def poll(self, batch_id: str) -> list[Trajectory]:
        """GET /rollouts/{batch_id} until terminal; returns trajectories."""
        ...
    def to_native(self, trajectories: list[Trajectory]) -> object:
        """Map to trainer's native batch type (trainer-specific)."""
        ...
```

Refactor the three existing adapters to expose `backend: TrainerBackend`
and the `submit` / `poll` / `to_native` methods explicitly (they
already implement the logic — this is a rename + Protocol conformance).

### Part 2 — ship six stub adapters, one per planned trainer

Each stub is ~40 lines: a module exposing a `make_{trainer}_rollout_func()`
factory that raises `NotImplementedError("see RFC-...")` and documents the
trainer-native batch type the adapter must ultimately emit.

File | Trainer | Key open item
---|---|---
`skyrl_http.py` | SkyRL | Confirm SkyRL's native batch contract; expected: `dict` mirroring OpenRLHF
`prorl_agent_http.py` | ProRL Agent | Confirm trajectory-level vs transition-level consumption
`areal_http.py` | AReaL | Confirm async vs sync preference
`agentgym_rl_http.py` | AgentGym-RL | Confirm whether tool-call tokens are masked or inlined
`ragen_http.py` | RAGEN | Confirm multi-turn reward aggregation
`marti_http.py` | MARTI | Confirm whether MARTI's multi-agent shape needs a per-agent fan-out beyond `extract_agent_trajectories`

For each stub, declare an optional-deps group in
`ergon_infra/pyproject.toml` under `[project.optional-dependencies]`:

```toml
training-skyrl      = ["skyrl>=0.1"]
training-prorl      = ["prorl-agent>=0.1"]
training-areal      = ["areal>=0.1"]
training-agentgym   = ["agentgym-rl>=0.1"]
training-ragen      = ["ragen>=0.1"]
training-marti      = ["marti>=0.1"]
```

(Version pins are placeholders pending the follow-on RFC for each trainer
that resolves actual PyPI availability.)

## Invariants affected

Adds an invariant to `docs/architecture/08_rl_loop.md`:

> **Invariant (trainer adapter contract).** All HTTP trainer adapters MUST
> consume `Trajectory` (see `rollout_types.py:L38-L51`) and expose
> `submit` / `poll` / `to_native` per the `TrainerHttpAdapter` Protocol.
> Trainer-specific logic (field renaming, batch shaping) lives in
> `to_native`; never in the server.

No change to existing invariants; this promotes prose-level guidance
("follow the pattern of `trl_http.py`") to an enforced Protocol.

## Migration

- Part 1 is source-only refactor on three existing adapters. They already
  conform to the Protocol semantically; this adds nominal conformance
  + enum.
- Part 2 adds six new files; no existing file is modified.
- No DB migration. No API change to `/rollouts/submit` or
  `/rollouts/{batch_id}`.
- Tests: add `tests/rl/test_trainer_adapter_contract.py` asserting all
  three real adapters are `isinstance(TrainerHttpAdapter)` and the six
  stubs raise `NotImplementedError` citing their follow-on RFCs.

## Alternatives considered

- **One RFC per trainer (six RFCs).** Rejected: each would say "write
  `{trainer}_http.py` matching the existing pattern". Grouping into one
  RFC reflects the fact that the design decision is the same in all six
  cases. Per-trainer follow-on RFCs resolve trainer-specific quirks
  (native batch type, sync/async, reward aggregation) on a case-by-case
  basis.
- **Skip the Protocol, just write the six stubs.** Rejected: without a
  Protocol, the next contributor has the same ambient-contract problem we
  have today. Formalizing the contract is cheap (one new file).
- **Cut five trainers from the paper.** Rejected by authors — Appendix E
  is descriptive and includes planned rows. The paper parity path is to
  ship stubs + RFCs, not retreat.

## Open questions

- Should the `TrainerBackend` enum values drive discovery (e.g., an
  entry-points-based registry), or is manual import-site registration
  sufficient? Suggest deferring to a follow-on RFC once a third consumer
  emerges.
- Do we want a `training-all` extras group bundling all six planned
  trainers, or only the three real ones? Suggest: `training` bundles
  the three real trainers; planned ones are opt-in by name.
- Version pin strategy for six packages that may not all be on PyPI under
  the expected name. Open-question resolution happens in the per-trainer
  follow-on RFCs.

## Paper parity

This RFC is the parity work for row 2 of the paper's Appendix E
integrations map. Sibling RFCs:
`2026-04-21-agent-framework-adapter-layer.md` (row 1, agents),
`2026-04-21-projection-operator-*.md` (row 3, projections). Until this
RFC's Part 2 lands, Appendix E describes SkyRL / ProRL / AReaL /
AgentGym-RL / RAGEN / MARTI as `planned (RFC-2026-04-21-rl-trainer-adapter-expansion)`.

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:
  - Add the `TrainerHttpAdapter` invariant to
    `docs/architecture/08_rl_loop.md`.
  - Open six follow-on RFCs (one per planned trainer) or, for trainers
    with no PyPI distribution yet, mark them `blocked` pending upstream
    release.
  - Update the paper's Appendix E to cite accepted state for the three
    real adapters and planned state for the six new stubs.
