---
status: open
opened: 2026-09-28
fixed_pr: null
priority: P2
invariant_violated: docs/architecture/07_testing.md
related_rfc: null
---

# CI checks an event lookup instead of Inngest health

## Symptom and reproduction

All three benchmark smoke jobs in [run 36461436734](https://github.com/DeepFlow-research/ergon/actions/runs/36461436734)
at `4e0be42a` failed before executing a benchmark. PostgreSQL became ready, then
`ci/wait_for_stack.sh` repeatedly failed its Inngest probe and exited with
`FATAL: inngest did not become ready within 60s`.

The separate integration job passed all 46 tests, but its duplicated readiness
loop exhausted the same probe and silently proceeded. The dashboard end-to-end
job also passed.

## Root cause and scope

Both probes requested `/v1/events/test`. Inngest routes that path to an event
lookup, so its success depends on event data rather than service health.
The [upstream API](https://github.com/inngest/inngest/blob/main/pkg/api/api.go)
defines `/health` for readiness. The failed CI run does not retain the suppressed
probe response, so its exact HTTP status is unknown.

## Repair

Use `/health` and bound each HTTP request. The integration workflow now calls
the same script as the smoke workflow, so an unavailable service fails setup
instead of being ignored. No runtime, benchmark, sandbox or scoring code changes.

## Verification

Shell syntax and workflow YAML are checked locally. Fresh CI must pass the
shared readiness check and execute the three benchmark smoke tests; a successful
health request alone does not establish function execution.
