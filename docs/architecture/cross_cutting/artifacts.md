# Cross-cutting — Artifacts

## Purpose

Workers produce artifacts (files, diffs, reports) that evaluators need to
read. The canonical path for this handoff is `SandboxResourcePublisher`, a
content-addressed blob store. Today the seam is PARTIALLY BROKEN — workers
write artifacts in-process as an `artifacts: dict`, which gets dropped at
the Inngest serialization boundary, forcing evaluators to either re-read
from the sandbox (which may be torn down) or reinvent retrieval ad-hoc.
This doc captures the intended canonical path, enumerates the live
offenders, and marks the RFC that closes the gap.

## Core abstractions

| Type | Location | Freeze | Owner |
|------|----------|--------|-------|
| `SandboxResourcePublisher` | `ergon_core/core/providers/sandbox/resource_publisher.py` | Stable | Sandbox provider |
| `RunResource` | ORM row; table `run_resources` | Stable wire shape | Persistence layer |
| `dashboard/resource.published` | Inngest event | Stable | Dashboard lane |
| `CriterionRuntime.read_resource(name)` | Proposed per RFC | Pending | Evaluator layer |
| `CriterionRuntime.list_resources()` | Proposed per RFC | Pending | Evaluator layer |
| `ERGON_BLOB_ROOT` | env var; filesystem root | Ops-owned | Runtime ops |

`SandboxResourcePublisher` is configured via the `ERGON_BLOB_ROOT` env var.
On `publish(name, path)` it reads the file from the sandbox, sha256-hashes
the content, writes to `ERGON_BLOB_ROOT/<hash>`, and inserts a `RunResource`
row for lookup by name and task id. Content addressing makes the store
deduplicating and replay-safe. The `dashboard/resource.published` event
emitter exists on `DashboardEmitter` but is not called from `publish()`
today — the live resource lane is therefore unpopulated and the dashboard
sees resources only via the cold-start REST snapshot. Wiring this is part
of the dashboard-event enforcement follow-up.

`RunResource` is the DB-side handle. The lookup key is
`(run_id, task_id, name)`. The content hash is recorded but is not part of
the lookup key — callers ask for the name, and the layer maps name ->
hash -> bytes. Names are stable per task; the hash is an implementation
detail.

`CriterionRuntime.read_resource(name)` and `list_resources()` are the
intended evaluator-side read path. They are pending per the RFC listed in
follow-ups; today evaluators reach through lower layers.

## Control flow (intended, once RFC lands)

```
Worker writes file in sandbox: /workspace/final_output/fix.patch
    |
    v
Worker calls publisher.publish(name="fix.patch", path="/workspace/final_output/fix.patch")
    |
    +--> publisher reads the file from the sandbox
    +--> hashes contents (sha256)
    +--> writes to ERGON_BLOB_ROOT/<hash>
    +--> inserts RunResource(run_id, task_id, name="fix.patch", hash=...) row
    +--> emits dashboard/resource.published event
    |
    v
Task completes; check_evaluators fan out criteria.
    |
    v
Criterion calls runtime.read_resource("fix.patch")
    -> looks up RunResource by (run_id, task_id, name)
    -> reads ERGON_BLOB_ROOT/<hash>
    -> returns bytes
```

Two independent movements: the publish (worker writes durable bytes + row)
and the read (evaluator does a keyed lookup). Neither depends on the
sandbox still existing, and neither depends on the in-process memory of the
worker. That is the whole point.

## Current state (what is actually broken)

- Workers accumulate an in-process `artifacts: dict[str, Any]` that gets
  dropped at the Inngest seam when the task-completion event is serialized.
  The dict never crosses the boundary.
- Evaluators that need artifacts fall back to one of two paths:
  1. Direct `sandbox.files.read(...)` — fails if the sandbox is torn down
     before the evaluator runs. In practice this is a race: fast evaluators
     win, slow ones silently fail.
  2. Direct DB queries on `RunResource` plus direct blob-store reads — this
     is correct but inlined into every evaluator that needs it, so there is
     no uniform retrieval layer.
- No single enforcement that artifacts go through the publisher. Nothing
  stops a worker from returning a dict and hoping.

## Example of the correct pattern (reference)

See `ergon_builtins/benchmarks/swebench_verified/` — workers publish
`fix.patch` via the publisher; the evaluator reads by name. This is the
pattern the rest of the codebase should converge on, and is what the RFC
promotes into the runtime's public contract.

## Invariants (intended)

- Artifacts from a worker that an evaluator needs MUST go through
  `SandboxResourcePublisher`. Enforced (once RFC lands) by: the only
  evaluator read path is `runtime.read_resource(name)`, which only returns
  rows backed by a publish.
- Lookups happen by `(run_id, task_id, name)`. Names are stable per task;
  the content hash is an implementation detail.
- The publisher is the intended producer of the `dashboard/resource.published`
  event so the resource lane in `UnifiedEventStream` stays in sync — partially
  wired today: the emitter method exists but `publish()` does not call it, so
  the lane is populated only on cold-start snapshot. Enforcement tracked under
  the dashboard-event wiring follow-up.
- `RunResource` rows are append-only within a task. A second publish under
  the same name yields a new row (or a replace, per the publisher's
  policy); readers always see a consistent snapshot.
- The blob store is content-addressed and immutable. A given hash always
  dereferences to the same bytes.

## Extension points

- **Add a new artifact type:** pick a stable `name`; publish via
  `resource_publisher.publish(name=..., path=...)` from the worker. The
  evaluator reads by the same name via `runtime.read_resource(name)`. No
  new types, no schema changes.
- **Add new metadata alongside a blob** (content-type, producer, size):
  extend `RunResource` columns; keep the blob bytes unchanged. Do not
  encode metadata into the blob name.
- **Swap the blob backend** (S3, GCS, local FS): the
  `SandboxResourcePublisher` is the only write-site; a new backend
  implements the same interface and the `ERGON_BLOB_ROOT` config becomes a
  URI.

## Anti-patterns (with offenders)

- **Accumulating an `artifacts: dict` in the worker and hoping it crosses
  the Inngest seam.** Currently the de-facto pattern in some workers. It
  does NOT cross. The dict is lost. Audit every worker that builds a
  dict-typed `artifacts` field on the return value; each is a silent data
  loss.
- **Evaluator reading directly from the sandbox.** Only safe while the
  sandbox is alive. Criteria timing makes this a race. Use the publisher.
  Any call to `sandbox.files.read(...)` from inside an evaluator is suspect.
- **Publishing without a name.** Blob is unreachable by the evaluator.
  Names must be stable per task. An auto-generated name (uuid, timestamp)
  defeats the lookup key.
- **Publishing the same name from two different workers in the same task.**
  Last-writer-wins, which is rarely what you want. Scope names by the
  worker's role.
- **Reading by hash rather than by name.** The hash is not part of the
  public key; it can change if the content changes. Name-based reads are
  the contract.

## Follow-ups

- `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` — adds
  `read_resource(name)` / `list_resources()` to `CriterionRuntime`. This is
  the RFC that closes the seam described above; once it lands, the
  "intended" control flow is the actual one.
- Proposed future: lint rule forbidding `artifacts: dict[str, Any]` style
  assembly in workers; force everything through the publisher. Mechanical
  check at CI time, since the failure mode is otherwise silent.
- Backfill audit. Inventory the existing workers that still return a dict
  of artifacts; migrate each to publish + named read. Track in the RFC's
  rollout checklist.
- Retention policy. `ERGON_BLOB_ROOT` has no documented GC. Decide on a
  per-run TTL and whether blobs survive task deletion; wire into the
  RunResource lifecycle.
