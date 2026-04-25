# Paper-tied RFCs

RFCs scoped specifically to back claims made in the Ergon NeurIPS 2026
paper. Originally framed as "nice-to-haves" (claims the paper makes about
Appendix~E integrations that the codebase doesn't yet ship); as of
2026-04-21 this directory also holds a distinct second class — RFCs that
are **paper-blocking** because Appendix~C's preservation table makes
formal claims about projection operators that require those projections
to exist in code by submission. Charlie has committed to landing the
paper-blocking RFCs before the paper goes live.

The directory name is kept for continuity (it's referenced from Appendix
E), but the `paper_blocking` front-matter field on each RFC is the source
of truth for which class it belongs to.

## Paper-blocking RFCs (must land before submission)

These RFCs back **Appendix~C preservation claims**. Each diagonal ✓
in Table~\ref{tab:preservation} under a community-native behavioural
quantity depends on the matching projection operator being shipped. The
claim that raw $\tau_E$ (via $\pi_{\text{json-log}}$) dominates the
preservation poset additionally depends on the `mcts.*` annotation
namespace being reserved.

| RFC | Paper claim backed | Effort estimate |
|---|---|---|
| `2026-04-21-projection-operator-option-tagged.md` | Appendix~C: $\pi_{\text{macro}}$ × *Opt-term* = ✓ | S (pure read over existing schema) |
| `2026-04-21-projection-operator-call-tree.md` | Appendix~C: $\pi_{\text{call-tree}}$ × *Call-dep* = ✓ (+ spawn-ordering invariant) | S (pure read; one runtime invariant to confirm) |
| `2026-04-21-projection-operator-mcts.md` | Appendix~C: $\pi_{\text{mcts}}$ × *MCTS-ent* = ✓ **and** $\pi_{\text{json-log}}$ × *MCTS-ent* = ✓ | S (Option A: reserve `mcts.*` annotation namespace + default-filled projection) |

Landing checklist (each RFC):
- Implementation PR merged on `main`.
- Tests passing (see each RFC's "Migration" section for the test matrix).
- Corresponding invariant added to `docs/architecture/08_rl_loop.md`.
- RFC moved from `paper-nice-to-haves/` to `accepted/` with a stub left
  here pointing at its accepted-state path.
- Appendix~E row in the paper repo flipped from `planned (RFC-...)` to
  `integrated`.

## Roadmap RFCs (not paper-blocking)

These back **Appendix~E integration-map rows** only. The paper honestly
describes each target row as `planned (RFC-...)`; landing the RFC flips
the row to `integrated` but does not alter any paper claim. They can
land before, during, or after paper submission.

| RFC | Paper-parity row | Effort estimate |
|---|---|---|
| `2026-04-21-agent-framework-adapter-layer.md` | Agents row: 5 frameworks (LangGraph, CrewAI, AutoGen, Google ADK, Claude Code) | M (contract + 5 stub adapters) |
| `2026-04-21-rl-trainer-adapter-expansion.md` | RL row: 6 trainers (SkyRL, ProRL Agent, AReaL, AgentGym-RL, RAGEN, MARTI) | M (Protocol + 6 stub adapters) |

## Conventions

- Filename and front-matter format follow `docs/rfcs/TEMPLATE.md`, plus
  two paper-specific front-matter fields: `paper_blocking: bool` and
  `paper_blocking_reason: str` (the justification for the flag).
- The front-matter `status` field is set to `active` (these are open
  scoping documents); promotion to `accepted` follows the same rules as
  the core RFC stream.
- When one of these moves to `accepted/`, leave a stub here pointing to
  its accepted-state path so the paper-parity audit trail remains
  intact.
- A paper-blocking RFC that has not yet landed on the submission date
  is a blocker for submission, not a reviewer risk to accept —
  `paper_blocking: true` is a commitment, not a forecast.

## Out of scope

Anything required for the existing experiments in §5 of the paper, or
for the production runtime, or for any benchmark in `ergon_builtins/`,
belongs in `docs/rfcs/active/` (core stream), not here. The distinction
between this directory and `docs/rfcs/active/` is *not* "core work vs
paper work" — it is "RFCs tied specifically to paper-parity claims vs
RFCs tied to the production runtime and experiments." Some items in
this directory (the three paper-blocking projection RFCs) are arguably
core enough to move to `active/`; that's an organizational decision
pending.
