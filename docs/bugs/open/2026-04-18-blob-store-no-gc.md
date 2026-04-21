---
status: open
opened: 2026-04-18
fixed_pr: null
priority: P4
invariant_violated: null
related_rfc: null
---

# Bug: blob store has no garbage collection

## Symptom

`SandboxResourcePublisher` writes blobs under `<ERGON_BLOB_ROOT>/<hash[:2]>/<hash>`
and never deletes them. See the write path at
`ergon_core/ergon_core/core/providers/sandbox/resource_publisher.py:166-175`
(`_write_blob`), invoked from `sync()` at line 93 and from `publish_value()` at
line 142. There is no corresponding delete path anywhere in the module, and no
retention policy, no size cap, and no sweeper. The blob store grows unboundedly
across runs.

## Repro

Conceptual — every `RunResource` publish writes bytes to disk via
`_write_blob`. No delete path exists. After N runs of any benchmark that
publishes artifacts (e.g. minif2f proofs, swebench patches), disk usage under
`ERGON_BLOB_ROOT` grows as `O(N * avg_artifact_size)` forever. Content-hash
dedup helps for byte-identical artifacts but does not bound growth for
workloads whose outputs vary across runs.

## Root cause

The publisher was designed as write-once content-addressable storage; see the
class docstring at `resource_publisher.py:27-33` ("Never updates. Content-hash
dedup makes repeated calls safe."). Deletion policy was out of scope for the
first cut, and no orphan-detection pass has ever been added.

## Scope

Research workloads with bounded disk budgets hit this eventually. Acceptable
today because research runs are manual and disk is cheap on the dev machine.
It grows into a real problem when (a) runs are scheduled on a shared host,
(b) CI accumulates artifacts across thousands of test runs, or (c) long-running
training loops publish heavy checkpoints.

## Proposed fix

Deferred. Options on the table:

  1. Reference counting via `RunResource` rows — delete the blob when the last
     referencing row is deleted.
  2. Age-based sweeper — delete blobs whose newest `RunResource` reference is
     older than N days.
  3. Size-based LRU — when `<ERGON_BLOB_ROOT>` exceeds a threshold, evict the
     least-recently-accessed entries.
  4. Never. Research-grade tool; the user manages disk out of band.

No decision today. Filed as a P4 tracking item so future disk pressure surfaces
this faster.

## On fix

  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Move the file from `docs/bugs/open/` to `docs/bugs/fixed/`.
  - Update `docs/architecture/03_providers.md` to document the chosen GC policy.
