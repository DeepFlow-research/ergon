---
status: fixed
opened: 2026-04-18
fixed_pr: 17
priority: P1
invariant_violated: docs/architecture/05_dashboard.md#invariants
related_rfc: docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md
---

# Bug: 9 of 12 DashboardEmitter methods are defined but never invoked

## Symptom

The dashboard's live delta stream is effectively two events wide: graph
mutations and context events. Everything else the UI renders — task
status changes outside graph nodes, sandbox create/command/close,
resource publication, task evaluation updates, thread messages, task
cancellations, and workflow start/completion — does not update live.
Users see these fields only if they reload the page, which triggers a
cold-start REST snapshot via `build_run_snapshot`.

The architecture invariant "every persistent backend state change has a
corresponding `dashboard/*` event"
(`docs/architecture/05_dashboard.md#invariants`) is violated silently.

## Repro

From the repo root:

```
rg -n '\.(task_status_changed|workflow_started|workflow_completed|resource_published|thread_message_created|task_evaluation_updated|task_cancelled)\(' \
   ergon_core ergon_builtins ergon_infra
```

Zero matches outside the emitter definition itself. The only dashboard
emitter call sites in the runtime are:

- `ergon_core/ergon_core/core/dashboard/emitter.py:467` — `cohort_updated`
- `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py:81` —
  `on_context_event` registered as listener on the context event repo
- `ergon_core/ergon_core/core/runtime/services/task_management_service.py:113`
  — `graph_mutation` registered as listener on `WorkflowGraphRepository`

For the sandbox methods, the only calls live inside
`ergon_core/ergon_core/core/providers/sandbox/event_sink.py:88,107,124`,
but nothing constructs a `DashboardEmitterSandboxEventSink` at runtime
(tracked separately in
`docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md`).

## Root cause

Each of the 9 dead methods was added to `DashboardEmitter`
(`ergon_core/ergon_core/core/dashboard/emitter.py:51`) ahead of its
corresponding call site, and the call sites were never added. The UI
happens to look healthy because the cold-start REST snapshot populates
every field; the absence of deltas is invisible on a static page load.

Enforcement of the underlying invariant is review-only, and the review
did not catch the gap.

## Scope

All users of the live dashboard. Any workflow that runs longer than a
page load (i.e. every real workflow) is affected. Existing tests pass
because no test asserts that these deltas reach the frontend.

## Proposed fix

Per-method wiring pass: for each of the 9 dead methods, find the
state-mutation site that should trigger it (e.g.
`task_status_changed` at the point of the status write in
`task_management_service`), add the emit call, and add a smoke test
that asserts the Inngest event was produced.

Enforcement is a separate concern and is covered by
`docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md`:
a pytest contract test that fails when any `DashboardEmitter` method
has zero call sites in `ergon_core/`, `ergon_builtins/`, or
`ergon_infra/`. Land the fix before the contract test so the test
passes at merge time.

## Fix

7 methods wired in this PR (sandbox 3 were already wired via PR #11):

- `workflow_started` — `ergon_core/ergon_core/core/runtime/inngest/start_workflow.py`
- `workflow_completed` — `ergon_core/ergon_core/core/runtime/inngest/complete_workflow.py`
- `task_status_changed` — `ergon_core/ergon_core/core/runtime/services/task_execution_service.py`
- `task_cancelled` — `ergon_core/ergon_core/core/runtime/inngest/cleanup_cancelled_task.py`
- `task_evaluation_updated` — `ergon_core/ergon_core/core/runtime/inngest/evaluate_task_run.py`
- `resource_published` — `ergon_core/ergon_core/core/runtime/inngest/persist_outputs.py`
- `thread_message_created` — `ergon_core/ergon_core/core/runtime/services/communication_service.py`

## On fix

When moving from `open/` to `fixed/`:
- Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
- Confirm the "every state change has a dashboard event" invariant in
  `docs/architecture/05_dashboard.md#invariants` is restored and the
  contract test from the related RFC is green.
