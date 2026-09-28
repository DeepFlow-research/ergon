---
status: fixed
opened: 2026-09-14
fixed_pr: 134
priority: P2
invariant_violated: docs/architecture/cross_cutting/artifacts.md
related_rfc: null
---

# Bug: E2B upload read error fails otherwise completed work

## Symptom

A Manager Gym human worker finished and checkpointed its inference, then failed while uploading
its resource: `E2BSandboxRuntime.write_file` raised `httpx.ReadError` from the SDK's filesystem
POST. The attempt kept its traceback and produced no `WorkerOutput`, so the task counted as an
infrastructure failure.

## Root cause

The E2B SDK propagates a read error even when the upload itself may have committed, and the
builtin runtime did not retry it. Worker and task retries are disabled on purpose, because they
would repeat arbitrary side effects such as model calls.

## Fix

`E2BSandboxRuntime.write_file` retries only `httpx.ReadError`, up to three attempts with one- and
two-second waits. Every attempt writes the same complete bytes to the same path, which E2B
overwrites, so a retry after a committed upload is harmless. Other exceptions and exhausted
retries propagate unchanged; commands, inference, workers and sandbox creation are not retried.
The acceptance driver also stops admitting samples after any unaccounted failure, in every stage.

## Verification

`test_e2b_runtime.py` simulates a response lost after the write committed, checks the retained
bytes, bounds persistent failure and leaves unrelated errors alone. `test_acceptance.py` covers
early stop, drain and resume for the pilot and catalog stages. A live E2B check uploaded 64 KiB,
dropped the first response, and verified the retried upload and readback.
