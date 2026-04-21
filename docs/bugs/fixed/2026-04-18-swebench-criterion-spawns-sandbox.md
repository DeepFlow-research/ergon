---
status: fixed
opened: 2026-04-18
fixed_pr: 16
priority: P2
invariant_violated: docs/architecture/06_builtins.md#anti-patterns
related_rfc: docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md
---

# Bug: SWE-bench criterion spawns its own sandbox

## Symptom

The SWE-bench-verified criterion at
`ergon_builtins/benchmarks/swebench_verified/criterion.py:72` instantiates
`SWEBenchSandboxManager()` directly inside `_spawn_eval_sandbox`. Criterion
execution for SWE-bench therefore always spins up a fresh sandbox environment
rather than consuming the task's existing sandbox. This violates the stated
contract that criteria should run in the task's sandbox, not spawn their own.

Observable effect: every SWE-bench eval pays the cost of an extra sandbox
create call. Harder to observe: if the first criterion-spawned sandbox hangs
or fails, the error surface is different from a task-sandbox failure, and any
future assumption that "a criterion sees the same sandbox state as the worker"
is wrong for this benchmark.

## Repro

Read `ergon_builtins/benchmarks/swebench_verified/criterion.py`. The function
`_spawn_eval_sandbox(run_id)` at lines 66-78 constructs a new
`SWEBenchSandboxManager()` (line 72), allocates a fresh `sandbox_key`
(line 73), calls `manager.create(...)` (line 74), and returns the new
sandbox. Every invocation of the SWE-bench criterion hits this path.

## Root cause

The criterion was written before the `CriterionRuntime` DI container pattern
existed as a way to hand a criterion access to the task's sandbox. The
criterion needs a sandbox to run the patch-verification tests; the simplest
available path at the time was to instantiate a sandbox manager directly and
bring up a new environment.

The file and line are known:
`ergon_builtins/benchmarks/swebench_verified/criterion.py:72`.

## Scope

SWE-bench-verified only. No other criterion in `ergon_builtins/` spawns a
sandbox today; they either run purely on the task output, read blobs via
`read_resource`, or call LLM judges. But the pattern is contagious — if it
gets copied into the next criterion that needs sandbox access, the
"one sandbox per task, reused by criteria" invariant is gone.

## Proposed fix

Blocked on `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`.
That RFC adds `get_sandbox()` to the `CriterionRuntime` Protocol, returning
the task's sandbox (or `None` if it has been torn down). Once the RFC lands:

1. Delete `_spawn_eval_sandbox` and the direct `SWEBenchSandboxManager()`
   call.
2. Replace with `sandbox = await runtime.get_sandbox()` at the criterion
   callsite.
3. Handle the `None` case: the current code path assumes a sandbox; with the
   DI container, a missing sandbox is an explicit short-circuit with a
   "sandbox unavailable" score.

This work is scheduled as Task 0 of the criterion-runtime-di-container RFC's
migration plan, so the fix lands as part of the RFC rather than as a separate
commit.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Confirm the criterion no longer constructs `SWEBenchSandboxManager`
    directly (grep: zero hits under `ergon_builtins/**/criterion*.py`).
  - Confirm `docs/architecture/06_builtins.md#anti-patterns` still lists "a
    Criterion spawning its own sandbox" as an anti-pattern and that the
    swebench-verified callout is removed or updated to reference the fixed
    state.
