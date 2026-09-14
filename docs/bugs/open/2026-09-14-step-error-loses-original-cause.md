---
status: open
opened: 2026-09-14
fixed_pr: null
priority: P2
invariant_violated: docs/architecture/cross_cutting/error_propagation.md
related_rfc: docs/rfcs/active/2026-09-07-manager-gym-port/
---

# Native task errors discard the underlying Inngest step failure

## Evidence and cause

The v14 banking sample `bb9166a2-8457-456d-96a2-08b147f2ba20`
failed task `01a52423-568a-4ed0-834b-444a40a23ca0`, attempt
`6fc98b31-0d0b-4948-81fc-4fc2fc6a7f6c`, between
2026-09-14 15:29:35 and 15:39:39 UTC. Its native record contains a blank
`StepError` from `role-work`, with no WorkerOutput. Admission stopped before
another scenario could start. The sample remains an unaccounted failure.

Both worker and task execution formatted only `str(exc)`, the Python wrapper
type and its local traceback. The installed Inngest SDK exposes the original
exception through `StepError.name`, `.message` and `.stack`; those fields were
discarded. This loss is reproduced by the regression test.

The elapsed time matches the configured 600-second operation cap, but the
original exception cannot be confirmed from the retained native record. The
identified workflow run `01M2G8KF05HFK30KFGPZJZ8P0Q` returned empty history
output, and its memoized-state endpoint returned HTTP 410 after completion.
Do not relabel this historical failure as a confirmed timeout or valid model
outcome. The available logs and attempt record are retained in ignored evidence.

## Repair

The existing Inngest error module supplies one formatter used by both execution
boundaries. It preserves original and replay stacks, original exception identity
and task context, with the exception name as the fallback for an empty message.
No retry, finalization, scheduling or scoring rule changes.

Separately, the MAG integration profile no longer applies its auxiliary
600-second timer to work roles. The 12-request budget and 300-second request
timeout remain. Native task cancellation and the manager's bounded drain own
work lifetime. Manager, estimator, decomposer and judge operations retain the
600-second cap. Transport/timeouts still raise and remain incomplete. This
recorded profile change requires fresh acceptance, not reuse of the v14 ledger.

## Verification

Regressions exercise direct and wrapped empty-message errors, retained response
notes and caller context, and the actual worker job's returned error record.
Inference tests verify auxiliary expiry, work continuing beyond that auxiliary
limit, native cancellation reaching an in-flight model request, and unchanged
request/provider failure rules. Live proof and full acceptance remain required.
