# Cross-Cutting — Sandbox Lifecycle

## 1. Purpose

The sandbox is a shared, long-lived resource that spans Worker execution AND criteria evaluation. Getting its lifecycle correct is an Ergon invariant that crosses the providers, runtime, and evaluator layers. A worker writes into the sandbox's filesystem during generator turns; criteria read that filesystem after the worker terminates; the sandbox must stay alive across that boundary. This document is the authoritative reference for lifecycle questions — timeouts, teardown timing, reconnect semantics, cancellation, and the rejected alternatives.

## 2. Core abstractions

| Name | Kind | Freeze status | Owner |
| --- | --- | --- | --- |
| Per-task sandbox | lifecycle mode | Frozen; the only supported mode today. | Providers layer. |
| `BaseSandboxManager.create(task_id, event_sink)` | method | Signature frozen; `event_sink` becomes required after RFC 2026-04-17-sandbox-event-sink-activation. | Providers layer. |
| `BaseSandboxManager.close(sandbox_id)` | method | Frozen. Idempotent. Safe from any cancellation path. | Providers layer. |
| `BaseSandboxManager.reconnect(sandbox_id)` | method | **Pending API.** Criteria will use this to attach to the task's still-live sandbox. See follow-ups. | Providers layer. |
| Sandbox-timeout floor | invariant | Enforced by manager `create` only after RFC 2026-04-17-sandbox-lifetime-covers-criteria lands. | Providers layer. |

The per-task sandbox is owned by the worker runtime for the duration of `Worker.execute()`, then ownership transfers to the evaluator harness for the duration of `check_evaluators`, then the harness calls `close`. There is never a moment when two components both believe they own the sandbox; handoff is explicit at `check_evaluators` entry.

## 3. Control flow

```
task starts -> Manager.create() -> sandbox_id persisted on the execution row
    |
    v
worker yields GenerationTurns; uses sandbox.commands.run(...) for tools
    |
    v
worker terminates (COMPLETED | FAILED | CANCELLED)
    |    sandbox is NOT yet closed
    v
check_evaluators fires; for each evaluator binding:
    +-> fan out one criterion execution
    |       criterion calls (future) CriterionRuntime.get_sandbox()
    |       -> Manager.reconnect(sandbox_id)
    |       -> runs e.g. swebench-harness test scripts inside the same sandbox
    |   criterion writes score to RunTaskEvaluation
    |
    v
all criteria done -> Manager.close(sandbox_id) via finalization path
    v
finalize_success
```

Data movement notes:

- The `sandbox_id` is the only handle that crosses the worker-to-evaluator boundary. It is written to the execution row by the worker runtime at create time and read back by `check_evaluators` when fanning out criteria.
- Worker's on-disk state (files written to `/workspace/final_output/`, tool-call intermediates, language-specific build artifacts) is what criteria actually consume. That is the load-bearing reason the sandbox must outlive the worker.
- Criteria write scores to `RunTaskEvaluation` rows, not to the sandbox. Sandbox is read-only from the criterion's perspective (by convention; E2B does not enforce this).

## 4. Invariants

1. **Sandbox lives until all criteria for the task have completed.** Teardown runs after `check_evaluators` finishes, NOT at task completion, NOT during `finalize_success`. Confirm by reading the teardown call at `check_evaluators.py:82`. This was a point of confusion in earlier drafts of this doc — the correction is that teardown follows criteria, not the other way around.
2. **Sandbox timeout on creation MUST be at least `task_timeout + max_criterion_timeout`.** Criteria running against a timed-out sandbox is a data-loss bug: the criterion reconnects, the sandbox is dead, the score is lost. Pending enforcement in RFC 2026-04-17-sandbox-lifetime-covers-criteria. Today this is a convention — managers set a generous timeout by inspection, not by formula.
3. **Criteria MUST reconnect via the manager, never by constructing `AsyncSandbox` directly.** Direct construction loses template pinning, loses event emission, and creates a fresh container that cannot see the worker's on-disk state. The reconnect path through the manager is the only correct way to attach to a live sandbox.
4. **`close(sandbox_id)` is idempotent and safe to call from any cancellation path.** Calling it twice is a no-op on the second call. Calling it from the cancellation cleanup hook is the only correct way to release a leaking sandbox.

## 5. Failure modes

- **Sandbox killed mid-task (OOM, network blip, E2B platform incident).** The next `sandbox.commands.run` call from inside the worker raises. System-owner steering: the task transitions to FAILED with the raised error captured as the failure reason. Managers of dynamic subtasks then figure out re-coordination per fractal-OS semantics — a failed subtask surfaces to its parent, which decides whether to retry, substitute, or fail upward. Static workflow nodes have no manager to catch the failure; downstream siblings in a static DAG inherit the failure per the rules laid out in `cross_cutting/error_propagation.md`.
- **Sandbox times out after task but before criteria run.** The worker completed fine, `check_evaluators` fans out, the first criterion's reconnect hits a dead sandbox. Pending fix: bump timeout on creation to `task_timeout + max_criterion_timeout`. Until that RFC lands, managers set a generous literal timeout.
- **Cancellation.** `ergon run cancel` emits a `TaskCancelledEvent`. The `cleanup_cancelled_task_fn` cleanup hook fires. Its `release-sandbox` step is currently a **STUB** — it logs but does not call `Manager.close(sandbox_id)`. Consequence: cancelled tasks leak sandboxes until the E2B-side inactivity timeout reclaims them. Pending fix: `docs/rfcs/active/2026-04-17-cleanup-cancelled-task-release-sandbox.md`.
- **Criterion raises mid-evaluation.** The criterion's error bubbles to the evaluator harness, which records a failed `RunTaskEvaluation` and continues fanning out remaining criteria. The sandbox stays up until every criterion completes (success or failure); only then does teardown fire. A raising criterion does not short-circuit teardown.

## 6. Lifecycle modes considered but NOT implemented

- **Per-run** — share one sandbox across every task in a DAG. Rejected: cross-task isolation is a correctness property, not just a cleanliness one. A compromised tool call in task A could poison task B's filesystem. The per-task teardown gives every task a clean slate at start.
- **Per-cohort** — warm pool of prebuilt sandboxes shared across runs. Deferred: this would cut training-time cold-start cost meaningfully, but adds eviction policy, poisoning mitigation, and debugging complexity. No current benchmark justifies the investment.
- **Per-turn** — fresh sandbox per LLM call. Rejected: too slow (seconds per turn in E2B), and it breaks the load-bearing assumption that tool results from turn N are on disk for turn N+1. Most workers cd around, cat files, build artifacts, and cross-reference outputs between turns; a fresh sandbox per turn would require rebuilding that state from scratch every call.
- The current design is "per-task, optional reuse if a benchmark opts in." No benchmark opts in today — the mechanism for opt-in (a `lifecycle_mode` enum on the manager) does not yet exist.

## 7. Extension points

### 7.1 Opt into sandbox reuse (future)

Not implemented. The future shape is a `lifecycle_mode: ClassVar[LifecycleMode]` enum on `BaseSandboxManager` subclasses with variants like `PER_TASK` (current behavior) and `PER_COHORT`. Adding this requires resolving the cross-task isolation question — cohort-level sandboxes would need explicit reset hooks between tasks. No RFC drafted.

### 7.2 Override teardown trigger

A subclass that needs non-standard teardown timing (e.g., to inspect sandbox state post-mortem before close) can subclass the harness entry points in `check_evaluators` or `finalize_success`. This is rarely the right move — the teardown timing is an invariant that the rest of the system depends on. Coordinate with the workflow finalization invariants documented in `02_runtime_lifecycle.md` before changing anything here.

## 8. Anti-patterns

- **Closing the sandbox in `finalize_success` instead of after `check_evaluators`.** If `finalize_success` fires before criteria complete, every criterion sees a dead sandbox. Correct path: teardown runs inside the `check_evaluators` completion path (see `check_evaluators.py:82`). No current offenders — this is preserved by the existing harness structure.
- **Constructing a fresh sandbox inside a criterion.** Breaks provenance (the criterion is now scoring a clean environment instead of the worker's actual output state) and isolates the criterion from everything the worker put on disk. The correct path is `CriterionRuntime.get_sandbox()` once RFC 2026-04-17-criterion-runtime-di-container lands. Until then, criteria reconnect via whatever manager API is available and should never call `AsyncSandbox.create` directly.
- **Leaking sandboxes on cancellation.** Current offender: the `cleanup_cancelled_task_fn.release-sandbox` step is a stub. Every cancelled task leaks its sandbox until E2B's inactivity timeout reclaims it. Pending fix in RFC 2026-04-17-cleanup-cancelled-task-release-sandbox.
- **Assuming teardown happens on task COMPLETED.** It does not. The sandbox is alive for the entire evaluator fan-out. Any code that assumes a COMPLETED task implies a torn-down sandbox is wrong; use the sandbox-closed event (or `check_evaluators` completion) instead.

## 9. Follow-ups

- `docs/rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md` — enforce the timeout invariant (`task_timeout + max_criterion_timeout`); add `reconnect(sandbox_id)` to `BaseSandboxManager` if the method is missing in the form criteria need.
- `docs/rfcs/active/2026-04-17-cleanup-cancelled-task-release-sandbox.md` — replace the stubbed `release-sandbox` step with a real `Manager.close(sandbox_id)` call.
- `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` — add `CriterionRuntime.get_sandbox()` so criteria attach via the manager, and `CriterionRuntime.read_resource(name)` so they read published outputs via a stable API instead of ad-hoc `RunResource` DB reads.
