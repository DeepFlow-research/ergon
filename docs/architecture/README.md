# Ergon Architecture

Canonical reference for how the Ergon runtime works. Single source of truth.
Parallel work streams coordinate through this doc — if you're adding a feature,
this is what you read first, and this is what you update if your change alters
an invariant.

## How to read these docs

Each architecture doc follows a fixed seven-section contract:

1. **Purpose** — one paragraph on what the layer is for.
2. **Core abstractions** — named types, their freeze status, who owns each.
3. **Control flow** — how data moves; a diagram where it clarifies.
4. **Invariants** — things that must be true, enforced by what.
5. **Extension points** — how to add a new thing at this layer.
6. **Anti-patterns** — what NOT to do, with current offenders cited.
7. **Follow-ups** — pending refactors or open questions touching this layer.

If you find a contradiction between these docs and the code, the **code is the
ground truth** and the doc is the bug — file a PR updating the doc.

## What these docs are (and aren't)

These are **design docs**, not a map of the code. Agents and humans can read
the code to learn what a function is called or where a class lives; they come
here to learn what the system is *supposed to do* and why.

**Write about:**
- **Invariants** — things that must be true, and what enforces them.
- **Control flow at concept level** — "benchmark fans out to workers, workers
  fan in to an aggregator", not the literal call sequence.
- **Anti-patterns with reasoning** — what not to do, and why.
- **Extension points and their contracts** — the shape of the seam, what the
  runtime guarantees.
- **Surface-area constraints** — "`Experiment` should not expose persistence
  internals" (the *bound*, not the method list).
- **Known limits and open questions** — invariants that don't hold yet,
  pointing at the tracking RFC/bug.

**Avoid in narrative prose:**
- **Function-name drift fixes.** "This function is called `complete_workflow_fn`
  not `finalize_success_fn`" — code is truth.
- **Implementation details re-specified.** Paraphrasing what the code already
  says clearly ("takes `task_id: str`, returns `TaskResult`").
- **Method-list inventories inside design arguments.** Keep surface-area
  constraints; drop the catalog.
- **Forward-referencing unaccepted RFCs as load-bearing.** The doc should
  describe how things work today.
- **Test/fixture name duplication.**

### Inventory vs. cross-reference

A single `path:line` pointer after an architectural claim is a
**cross-reference** — it helps the reader find the implementation. A bulleted
list of five `path:line` entries is **inventory** — the doc is leaning on the
map to make the argument.

- ✅ "`dashboard_emitter` is a process-level singleton
  ([`emitter.py:451`](...))." — claim first, pointer as aside.
- ❌ "Offenders: `foo.py:23`, `bar.py:45`, `baz.py:67`, `qux.py:89`,
  `quux.py:101`." — delete the list, say "five call sites omit this kwarg
  (grep `SandboxManager(`)".

**A dedicated "Code map" section is fine** — a compact table of "where the
Inngest functions live", "where the criterion implementations are" — as
onboarding reference material, kept separate from the design narrative. Test:
if you removed the code map, would the architectural argument still hold? If
yes, it's doing its job. If no, the doc is leaning on inventory and needs a
rewrite.

## Layer map

| File | Scope |
|------|-------|
| [`01_public_api.md`](01_public_api.md) | The types contributors touch: `Benchmark`, `Worker`, `Evaluator`, `Criterion`, `Experiment`, `BenchmarkTask`. |
| [`02_runtime_lifecycle.md`](02_runtime_lifecycle.md) | Inngest fan-out, task state machine, cancellation, finalization. |
| [`03_providers.md`](03_providers.md) | Sandbox managers, generation registry, event sinks, resource publisher. |
| [`04_persistence.md`](04_persistence.md) | Graph WAL, run snapshots, Alembic policy. |
| [`05_dashboard.md`](05_dashboard.md) | Inngest→Next.js→Socket.io pipeline; HA constraints. |
| [`06_builtins.md`](06_builtins.md) | Benchmark registration, template setup, stub worker pattern. |
| [`07_testing.md`](07_testing.md) | Fast / state / e2e tiers; what each layer tests. |
| [`08_rl_loop.md`](08_rl_loop.md) | Rollout service, reward plumbing, TRL HTTP adapter. |

Cross-cutting concerns that span layers live in [`cross_cutting/`](cross_cutting/):

| File | Scope |
|------|-------|
| [`cross_cutting/artifacts.md`](cross_cutting/artifacts.md) | Worker→criterion artifact handoff via `SandboxResourcePublisher` + `CriterionRuntime.read_resource`. |
| [`cross_cutting/sandbox_lifecycle.md`](cross_cutting/sandbox_lifecycle.md) | Per-task default, reconnect, teardown timing. |
| [`cross_cutting/error_propagation.md`](cross_cutting/error_propagation.md) | Failure semantics, cancel cascade, fractal-OS semantics. |

## Status: partial

This doc tree was bootstrapped in a Q&A session with the system owner on
2026-04-17. High-confidence layers (01, 02, 03, 08, cross_cutting/sandbox_lifecycle)
are drafted in full; others are skeletons marked `[Q&A pending]`. Skeletons
will be filled in as the remaining Q&A sessions land.

## Related trees

- [`../rfcs/`](../rfcs/) — feature proposals and fix designs, grouped by status.
- [`../bugs/`](../bugs/) — triaged bug backlog, grouped by status.
- [`../superpowers/plans/`](../superpowers/plans/) — executable implementation plans.
- [`../superpowers/brainstorms/`](../superpowers/brainstorms/) — pre-RFC problem framing.

## The rule

Every feature PR either:
- **cites** the architecture section(s) it relies on (OK for mechanical changes
  inside an established pattern), or
- **updates** those sections (required if the change alters an invariant, adds
  an extension point, or removes an anti-pattern offender).

Cross-cutting changes must update `cross_cutting/` explicitly. PRs that break
an invariant without updating the doc are NAK'd regardless of test state.
