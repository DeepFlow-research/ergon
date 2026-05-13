---
status: in-flight engineering doc (decisions accepted; implementation pending)
opened: 2026-05-11
author: charlie + agent
architecture_refs:
  - ../../../architecture/01_public_api.md
  - ../../../architecture/cross_cutting/sandbox_lifecycle.md
supersedes: ../2026-05-08-authoring-api-redesign/
superseded_by: null
---

# Authoring API redesign — v2

> **Note on the "RFC" path.** This doc lives under `docs/rfcs/active/` for
> path continuity, but it is **not** an open proposal. The decisions below
> are accepted; the implementation is pending. Treat it as engineering
> documentation for an in-flight redesign that will graduate into
> `docs/architecture/` once it ships.

## Why v2

v1 of this RFC ([`../2026-05-08-authoring-api-redesign/`](../2026-05-08-authoring-api-redesign/))
shipped to a worktree but never merged. An end-to-end audit
([`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md))
found significant drift between the v1 spec and the v1 implementation:

- **Public API surface — solid.** `Experiment`, `Benchmark`, `Task`,
  `Worker`, `Sandbox`, `Criterion`, `Rubric`, `Evaluator` and the
  `_type`-discriminated definition serialization all hold up. Authors
  building benchmarks against v1 produce code that v2 will accept
  unchanged.
- **Implementation underneath — partially rotted.** Three persistence
  tiers where two suffice (`ExperimentRecord` ⊕ `ExperimentDefinition` ⊕
  `RunGraphNode`). A second `_prepare_definition` runtime path that
  rebuilds `Sandbox`/`Worker` instances from definition rows — read
  exclusively from definitions, never from run-tier copies. A
  `_persist_single_sample_workflow_definition` CLI path that writes only
  to a stub `saved_specs` table no other code reads. Sandbox provisioned
  in `worker_execute` then *not* released after inline criteria; per-run
  cleanup masks the leak. A `Worker.from_buffer` constructor with no
  callers. A `CriterionExecutor` Protocol with one trivial implementation.

The audit's conclusion: **the v1 design intent is right; the v1
implementation accumulated parallel paths and stub abstractions that
need to come out before the design can be claimed as load-bearing.**

v2 is a smaller, better-specced cut at the same target. The v1 docs in
`../2026-05-08-authoring-api-redesign/` remain as the historical
reference (see the archive banner on v1's README); the v2 docs in this
folder are the active spec the next implementation aims at.

## Reading order

| # | File | What it owns | Status vs v1 |
|---|---|---|---|
| 00 | [`00-readme.md`](00-readme.md) | This doc — entry point, doc map, deltas vs v1 | NEW |
| 01 | [`01-api-surface.md`](01-api-surface.md) | The public types authors construct (`Experiment`, `Benchmark`, `Task`, `Worker`, `Sandbox`, `Criterion`, `Rubric`, `Evaluator`); definition-time vs runtime split; `_type` discriminator pattern | Carried forward from v1 (cross-refs updated; phase tags marked historical) |
| 02 | [`02-persistence-layer.md`](02-persistence-layer.md) | Two-tier persistence model (`ExperimentDefinition` ⊕ run-tier `RunRecord`/`RunGraphNode`/`RunGraphEdge`/`RunGraphAnnotation`/`RunGraphMutation`); identifier model; `from_definition` convention; **runtime reads only run-tier tables** | Augmented from v1's 02 — `ExperimentRecord` collapsed into `ExperimentDefinition`; runtime read boundary made explicit |
| 03 | [`03-runtime.md`](03-runtime.md) | What happens when a run starts; sandbox provisioning via `Sandbox`-on-Task; `SandboxLifecycleHub`; `WorkerContext`; **criteria run inline in `worker_execute`**; cross-job sandbox lifetime | Augmented from v1's 03 — inline criteria made explicit; cross-job sandbox lifetime spelled out; cross-ref to 06 for event contracts |
| 04 | [`04-walkthrough.md`](04-walkthrough.md) | Single source of truth for "what running end-to-end looks like" — author code, what hits the database, what events fire, where each Task lives at each step | Carried forward from v1 unchanged (still canonical) |
| 05 | [`05-cli-authoring-interface.md`](05-cli-authoring-interface.md) | What `ergon define` and `ergon run` actually do; composition-convenience semantics (build an `Experiment` and persist it); no second slug-based path | NEW — fills a gap v1 left open |
| 06 | [`06-inngest-event-contracts.md`](06-inngest-event-contracts.md) | Per-event payload schemas, producers, consumers, fan-out semantics, idempotency keys; **single `worker_execute` job (no separate `evaluate_task_run`)** | NEW — replaces v1/05 §14.B; specs the unified worker_execute |
| 07 | [`07-test-strategy.md`](07-test-strategy.md) | Architecture-guard tests (boundary tests, retired-symbol tests); walkthrough as an integration test; regression net for the v1 audit findings | NEW — closes the "v1 stubs slipped through review" failure mode |
| 08 | [`08-decisions-log.md`](08-decisions-log.md) | Accepted decisions + rejected alternatives + the locked decisions inherited from the v1 audit (collapse, read boundary, dynamic-subtask shape, inline criteria, single sandbox lifetime owner, schema reset, deletions) | Carried forward from v1's 06 + locked-decisions section appended |
| 09 | [`09-implementation-plan.md`](09-implementation-plan.md) | Ordered, smaller PR plan (no Tier D incremental drop migrations; single fresh initial schema instead) | NEW — supersedes v1/05's phased work-order entirely |

## What changed from v1 — the locked deltas

The full audit lives in
[`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md);
the architectural decisions it crystallized are reproduced verbatim in
[`08-decisions-log.md`](08-decisions-log.md) "Locked decisions
inherited from v1 audit". The summary form:

| # | Delta | Owner doc |
|---|---|---|
| Δ.1 | **`ExperimentRecord` collapses into `ExperimentDefinition`.** Authoring metadata fields move directly onto `Experiment`. Persistence is two-tier, not three. | [`02-persistence-layer.md`](02-persistence-layer.md) |
| Δ.2 | **Runtime reads only run-tier tables.** No `_prepare_definition` fall-through that hydrates `Sandbox`/`Worker` from `ExperimentDefinition` rows. After `prepare_run` copies the graph from definition into run tables, all subsequent reads come from run-tier. | [`02-persistence-layer.md`](02-persistence-layer.md) |
| Δ.3 | **Dynamic subtasks are graph-native.** Tasks spawned at runtime live only in `RunGraphNode` with a nullable definition `task_id`. There is no "synthesize a definition row" path. | [`02-persistence-layer.md`](02-persistence-layer.md) |
| Δ.4 | **Single `worker_execute` job; criteria run inline.** The walkthrough is canonical: `worker.execute()` returns, the same job iterates `task.evaluators`, the same job releases the sandbox. There is no separate `EvaluateTaskRunRequest` / `evaluate_task_run.py` Inngest function. | [`03-runtime.md`](03-runtime.md), [`06-inngest-event-contracts.md`](06-inngest-event-contracts.md) |
| Δ.5 | **Cross-job sandbox lifetime, single owner.** `worker_execute` acquires; the same `worker_execute` releases (after inline criteria); per-run cleanup is a backstop, not the primary release path. | [`03-runtime.md`](03-runtime.md) |
| Δ.6 | **Schema reset, not incremental drops.** Wipe the v1 Alembic migrations; generate one fresh "initial schema" migration that matches v2's two-tier model. No "drop a column" migration chain. | [`02-persistence-layer.md`](02-persistence-layer.md), [`09-implementation-plan.md`](09-implementation-plan.md) |
| Δ.7 | **Deletions.** `CriterionExecutor` Protocol (one trivial impl); `Worker.from_buffer` (no callers); `saved_specs` package (write-only, no readers); `_prepare_definition` runtime path; `definition_task_id` column. | [`09-implementation-plan.md`](09-implementation-plan.md) |
| Δ.8 | **CLI is composition convenience, not a parallel persistence path.** `ergon define <slug>` builds an `Experiment` from a registered factory and calls the same `persist_definition` the public Python API uses. There is no second slug→spec persistence flow. | [`05-cli-authoring-interface.md`](05-cli-authoring-interface.md) |

## What did **not** change from v1

The audit explicitly cleared these — they're carried forward in v2
unchanged:

- **Public API shape.** All seven definition-time types
  (`Experiment`, `Benchmark`, `Task`, `Worker`, `Sandbox`, `Criterion`,
  `Rubric`, `Evaluator`), `WorkerContext` curated methods,
  `CriterionContext` as a pure data carrier, the `WeightedCriterion` /
  rubric aggregation shape — all unchanged.
- **`_type`-discriminated definition serialization.** `_type`,
  `to_definition()`, `from_definition()` round-trip — unchanged.
- **`SandboxLifecycleHub` as the framework-internal coordinator.**
  Unchanged. What's new is *who calls release*, not the hub itself.
- **Identifier model.** Single `task_id` minted at definition-time and
  carried unchanged through run-tier and into the runtime objects via
  `_task_id` PrivateAttr. Unchanged from v1's 02.
- **Walkthrough.** [`04-walkthrough.md`](04-walkthrough.md) was
  conceptually correct and stays as the single source of truth for
  "what running looks like."

## How to consume this folder

For the spec reader (e.g. another agent reimplementing v2):

1. Read `00-readme.md` (you're here).
2. Read `08-decisions-log.md` "Locked decisions inherited from v1
   audit" before reading any other content doc — those decisions are
   the load-bearing constraints that distinguish v2 from v1.
3. Read `01` → `02` → `03` → `04` for the design.
4. Read `05` → `06` for the surface contracts (CLI, events).
5. Read `07` for the test strategy.
6. Read `09` for the implementation order.

For the human reviewer / workshop participant:

- Each new doc (`05`, `06`, `07`, `09`) ends with a **"Open questions
  for workshop"** section — that's where the targeted feedback should
  go.
- The augmented docs (`02`, `03`) flag inserted sections with `[v2:
  added]` markers so v1↔v2 diff review is straightforward.

## Status

**Status:** Workshop completed (2026-05-11); all open questions
resolved or deferred to follow-up. Implementation pending.

The "Decisions locked at workshop" section at the bottom of each doc
records the resolutions. For provenance:

| Doc | Section | What it records |
|---|---|---|
| `02` | §6 — Decisions locked at workshop | `name`/`description` are dedicated columns; `is_dynamic` denormalized; no definition versioning; WAL kept forever for v2 launch. |
| `05` | Decisions locked at workshop | No plugin slug registration; no `--override`; no cohort runs; no `ergon launch <slug>` shortcut. |
| `06` | `task/failed` "Failure semantics — the four-axis lock" + Decisions locked at workshop | Spawn-subtree cascade-FAIL; dependency-dependents stay PENDING; non-descendants continue; `runs.status` strict. Minimal `workflow/completed` payload; framework-only retry policy; annotation-WAL stream chunks. |
| `07` | Decisions locked at workshop | Textual architecture guards; hand-written walkthrough integration test; 8-finding regression net; sequential test execution. v1 integration / e2e suite refresh is a post-v2 follow-up. |
| `08` | "Open questions" (most resolved) | PrivateAttr pattern kept; sandbox IO methods on base; CriterionContext kept; backpressure deferred; instance_key drop deferred. |
| `09` | Decisions locked at workshop | Single PR branch (charlie reviewing); no prod data; SQLite for unit + Postgres for walkthrough integration; phase 6 last. |

Follow-up items deferred from v2 (tracked in
[`08-decisions-log.md` "Future work"](08-decisions-log.md)):

- Synchronous `spawn_task(..., await_completion=True)`.
- Multiple agents per task / sandbox sharing.
- Cross-task data handoff via `Task.inputs` / `Task.outputs`.
- `GraphSpawnGovernor` for fork-bomb backpressure.
- `Task.instance_key` redundancy cleanup.
- Cohort runs from CLI (`--replicas N`).
- v1 integration / e2e test suite refresh.
- v1 worktree deletion (~4 weeks after v2 ships).
