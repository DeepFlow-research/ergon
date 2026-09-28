---
status: fixed
opened: 2026-09-28
fixed_pr: 134
priority: P2
invariant_violated: docs/architecture/07_testing.md
related_rfc: null
---

# Bug: CI checks an event lookup instead of Inngest health

## Symptom

All three benchmark smoke jobs failed before running a benchmark: PostgreSQL became ready, then
`ci/wait_for_stack.sh` kept failing its Inngest probe and exited with
`FATAL: inngest did not become ready within 60s`. The integration job used a duplicated
readiness loop that exhausted the same probe and silently carried on.

## Root cause

Both probes requested `/v1/events/test`, which Inngest routes to an event lookup, so its result
depends on event data rather than service health. Inngest's
[API](https://github.com/inngest/inngest/blob/main/pkg/api/api.go) exposes `/health` for readiness.

## Fix

Probe `/health` with a bounded request timeout. The integration workflow now calls the same
script as the smoke workflow, so an unavailable service fails setup instead of being ignored.

## Verification

CI passes the shared readiness check and runs the three benchmark smoke tests.
