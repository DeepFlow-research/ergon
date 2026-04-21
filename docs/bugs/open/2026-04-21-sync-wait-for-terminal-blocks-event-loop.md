---
status: open
opened: 2026-04-21
fixed_pr: null
priority: P2
invariant_violated: null
related_rfc: null
---

# Bug: sync `wait_for_terminal` blocks event loop in async tests

## Symptom

`tests/real_llm/fixtures/harness_client.py` defines
`BackendHarnessClient.wait_for_terminal` as a **synchronous** method that loops
on `time.sleep(poll_s)` for up to `timeout_s` seconds (default 600s).

The only current caller, `tests/real_llm/benchmarks/test_smoke_stub.py`, is
marked `@pytest.mark.asyncio` and runs inside an asyncio event loop —
calling `harness_client.wait_for_terminal(...)` from that coroutine blocks
the loop for the full poll cycle. Any concurrent asyncio tasks (today: none
consequential; tomorrow: Playwright actions, additional harness polls,
timeouts, cancellations) are starved for the duration.

This is the textbook "sync blocking call in async code" anti-pattern: a single
`time.sleep` inside an awaited stack frame freezes all cooperative multitasking.

## Repro

Inside `tests/real_llm/benchmarks/test_smoke_stub.py`:

```python
state = harness_client.wait_for_terminal(run_id, timeout_s=120)
```

While this call is in flight, no other coroutine scheduled on the same loop
can make progress. Observable today as: if you launch a second task alongside
the poll (e.g. a Playwright `page.goto`), the goto waits for the full poll
interval before starting. Reproducible by adding `asyncio.create_task(...)`
before the `wait_for_terminal` call and logging task start times — tasks
created before the call don't run until the poll loop yields, which it never
does.

## Root cause

`harness_client.py:18-21` uses `httpx.Client` (sync) and `harness_client.py:35`
uses `time.sleep(poll_s)`. Both are synchronous primitives executed on the
event-loop thread without `run_in_executor`, so the loop cannot service other
coroutines. The client class was written as sync-first (mirroring the TS
`testHarnessClient.ts`) but the test harness that invokes it is async.

## Scope

- Every real-LLM canary / smoke test that awaits the harness (currently
  `test_smoke_stub.py`).
- Any future test that runs Playwright concurrently with harness polling
  (explicitly anticipated in the RFC for the real-LLM debug harness).
- Does NOT affect production — `BackendHarnessClient` is test-only scaffolding.

## Proposed fix

Convert `get_run_state` and `wait_for_terminal` to `async def` using
`httpx.AsyncClient` and `asyncio.sleep`. Update the single caller in
`test_smoke_stub.py` to `await`. Add unit tests in
`tests/unit/test_harness_client.py` using `pytest-httpx` that cover the
three behaviors: immediate terminal, poll-until-terminal, timeout.

## On fix

  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Move the file from `docs/bugs/open/` to `docs/bugs/fixed/`.
