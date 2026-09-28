---
status: fixed
opened: 2026-09-14
fixed_pr: 134
priority: P2
invariant_violated: docs/architecture/cross_cutting/error_propagation.md
related_rfc: null
---

# Bug: Native task errors discard the underlying Inngest step failure

## Symptom

A failed Manager Gym work task recorded only a blank `StepError` from its `role-work` step, with
no `WorkerOutput`. The original exception could not be recovered from the native record or from
Inngest, whose run history is gone once the run completes.

## Root cause

Worker and task execution formatted only `str(exc)`, the Python wrapper type and the local
traceback. The Inngest SDK carries the original exception in `StepError.name`, `.message` and
`.stack`, and those fields were dropped.

## Fix

One formatter in the Inngest error module now serves both execution boundaries. It keeps the
original exception type, the original and replay stacks and the task context, and falls back to
the exception name when the message is empty. Retry, finalization, scheduling and scoring are
unchanged.

Separately, Manager Gym work roles no longer run under the 600-second operation timer used for
manager, estimator, decomposer and judge calls; the request budget, per-request timeout, native
task cancellation and the manager's drain deadline bound them instead.

## Verification

Regression tests cover direct and wrapped empty-message errors, retained response notes and
caller context, and the error record returned by the real worker job. `step_error.py` in
`tests/real_llm/manager_gym/` checks the same on a live stack: the original `TimeoutError` and
its note survive replay, one attempt fails, the sample fails and the sandbox closes.
