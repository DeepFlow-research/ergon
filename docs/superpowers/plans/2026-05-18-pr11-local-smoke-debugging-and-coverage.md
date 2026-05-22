# PR11 Local Smoke Debugging And Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:systematic-debugging before changing runtime behavior, then use superpowers:test-driven-development for each code fix. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop using GitHub CI as the debugger, reproduce the PR11 smoke failure locally, add integration coverage for dynamic task propagation, and only push once all three local smokes are green end to end.

**Architecture:** Treat the smoke failure as a multi-component runtime bug across `Worker.execute`, `TaskManagementService.plan_subtasks`, Inngest event dispatch, graph dependency propagation, and evaluator timing. The current evidence says unit/integration tests cover dispatch pieces but not the full parent-plans-children-children-execute-parent/evaluator-observes-completion path. The plan first adds a focused integration reproduction, then uses the full local stack to confirm the real Inngest behavior before making the smallest root-cause fix.

**Tech Stack:** Python, pytest, SQLModel/Postgres, Inngest dev server, Docker Compose, existing `scripts/smoke_local_up.sh` / `scripts/smoke_local_run.sh`, Ergon smoke fixtures.

---

## Working Hypothesis To Test, Not Assume

The current smoke parent and recursive workers plan subtasks and then wait inside the same `worker-execute` Inngest function for those subtasks to complete. Child `task/ready` events are emitted from that function, but the children remain pending while the parent function is still running. That looks like an Inngest orchestration deadlock or event-delivery timing problem, not a simple serialization bug.

The fix must be driven by local evidence. If local traces disprove this hypothesis, update the plan before implementing a different fix.

## Files

- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/worker_base.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/recursive.py`
- Modify: `tests/fixtures/smoke_components/smoke_base/criterion_base.py`
- Modify or create: `ergon_core/tests/integration/runtime/test_dynamic_task_propagation.py`
- Possibly modify: `ergon_core/tests/unit/core/application/jobs/test_worker_execute_live_sandbox_attach.py`
- Possibly modify: `tests/e2e/_asserts.py`
- Run: `scripts/smoke_local_up.sh`
- Run: `scripts/smoke_local_run.sh`

## Task 1: Establish The Local Full-Stack Reproduction

- [ ] **Step 1: Start the local stack**

Run from repo root:

```bash
scripts/smoke_local_up.sh
```

Expected: Postgres, API, dashboard, and Inngest dev are healthy. If Docker is already running stale containers, run `docker compose ps` and inspect before restarting.

- [ ] **Step 2: Export the smoke environment**

Use the values printed by `scripts/smoke_local_up.sh`, correcting the duplicated `export` typo in the printed `SCREENSHOT_DIR` line:

```bash
export ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@localhost:5433/ergon
export INNGEST_API_BASE_URL=http://localhost:8289
export INNGEST_DEV=1
export INNGEST_EVENT_KEY=dev
export ERGON_API_BASE_URL=http://127.0.0.1:9000
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001
export SCREENSHOT_DIR=/tmp/playwright
```

- [ ] **Step 3: Run the smallest failing smoke**

Run one cohort member first:

```bash
scripts/smoke_local_run.sh swebench-verified 1
```

Expected current failure: timeout with root still running and child graph nodes pending. Capture the run id from the pytest failure.

- [ ] **Step 4: Capture runtime evidence at component boundaries**

For the failed run, collect:

```bash
docker compose logs --since=15m api > /tmp/ergon-api-smoke.log
docker compose logs --since=15m inngest > /tmp/ergon-inngest-smoke.log
rg -n "task/ready|worker-execute|plan_subtasks|RunGraphNode|pending|completed|failed|error|Exception" /tmp/ergon-api-smoke.log /tmp/ergon-inngest-smoke.log
```

Expected: enough evidence to locate whether `task/ready` events are not emitted, emitted but not received by Inngest, received but not invoking `worker-execute`, or invoking but failing before graph state changes.

## Task 2: Add Missing Integration Coverage For Dynamic Task Propagation

- [ ] **Step 1: Write a failing integration test around the real propagation contract**

Create or extend `ergon_core/tests/integration/runtime/test_dynamic_task_propagation.py` with a test shaped like:

```python
async def test_parent_planned_ready_children_are_dispatched_and_reach_terminal_status():
    """A parent worker planning dynamic subtasks must not leave children pending."""
```

The test should construct a real run graph using existing test-support factories, execute the parent path through the application job/service boundary, and assert:

```python
assert root_node.status in {"completed", "failed"}
assert sorted(child.task_slug for child in children) == sorted(EXPECTED_SUBTASK_SLUGS)
assert all(child.status != "pending" for child in children)
assert any(execution.node_id == child.id for child in children for execution in executions)
```

This test must fail on the current broken behavior before the fix.

- [ ] **Step 2: Cover replay/idempotency explicitly**

Add a second test that simulates Inngest step replay around `plan_subtasks`:

```python
async def test_plan_subtasks_step_replay_does_not_duplicate_children_or_drop_ready_events():
    """Replay must preserve one graph mutation and one ready dispatch per root child."""
```

Assert:

```python
assert len(children) == len(EXPECTED_SUBTASK_SLUGS)
assert len({child.task_slug for child in children}) == len(EXPECTED_SUBTASK_SLUGS)
assert ready_dispatch_count == expected_root_ready_count
```

This locks in the fix from `c03a219`: no duplicate child nodes under step replay.

- [ ] **Step 3: Run the new tests and confirm they fail for the right reason**

Run:

```bash
uv run pytest ergon_core/tests/integration/runtime/test_dynamic_task_propagation.py -v --tb=short
```

Expected before fix: at least one test fails because child tasks remain pending or because no child execution row is created. If it fails due to fixtures/imports instead, fix the test harness first.

## Task 3: Decide The Runtime Shape From Evidence

- [ ] **Step 1: Compare local evidence to the two plausible fixes**

Use this decision table:

```text
Evidence: child task/ready events never reach Inngest
Fix: event dispatch wiring bug in TaskManagementService / Inngest client config.

Evidence: events reach Inngest but child worker-execute does not start until parent unwinds
Fix: smoke/runtime contract must not wait inside the parent worker for children that are scheduled through sibling events.

Evidence: child worker-execute starts and fails immediately
Fix: inspect child payload/context construction; repair the failing service boundary.

Evidence: children complete but parent/evaluator reads stale state
Fix: criterion/read-model polling or transaction visibility issue.
```

- [ ] **Step 2: Write down the chosen root cause in the PR notes**

Update the PR description or a short local note with:

```text
Root cause:
Evidence:
Fix selected:
Why not the other fixes:
```

Do this before implementation.

## Task 4: Implement The Smallest Root-Cause Fix

- [ ] **Step 1: If the deadlock hypothesis is confirmed, remove child waiting from smoke workers**

Modify `tests/fixtures/smoke_components/smoke_base/worker_base.py` so the parent worker plans children, emits its three expected chunks, and returns a successful `WorkerOutput` without polling direct children.

Expected final product:

```python
yield WorkerOutput(
    output=waiting_message,
    success=True,
    metadata={
        "planned_children": sorted(result.nodes.keys()),
        "child_wait_mode": "criterion",
    },
)
```

Remove unused direct polling imports if this path is selected.

- [ ] **Step 2: If the deadlock hypothesis is confirmed, remove nested child waiting from the recursive worker**

Modify `tests/fixtures/smoke_components/smoke_base/recursive.py` so `l_2` plans `l_2_a -> l_2_b`, emits its fixed three chunks, sends its recursive completion message, and returns without polling nested children.

Expected final product:

```python
yield WorkerOutput(
    output="nested smoke recursion planned",
    success=True,
    metadata={
        "planned_children": sorted(result.nodes.keys()),
        "child_wait_mode": "criterion",
    },
)
```

Keep `RecursiveSmokeWorkerBase.RECURSIVE_TURN_COUNT == 3` unless local assertions prove the smoke contract should change.

- [ ] **Step 3: Move child completion waiting to the smoke criterion**

Modify `tests/fixtures/smoke_components/smoke_base/criterion_base.py` so `evaluate` waits for the graph and artifact state it already asserts.

Expected helper shape:

```python
async def _wait_for_artifact_state(
    self,
    context: CriterionContext,
    *,
    timeout_s: float = 180.0,
    interval_s: float = 2.0,
) -> tuple[list[RunGraphNode], list[RunGraphNode], dict[UUID, ProbeResult]]:
    deadline = time.monotonic() + timeout_s
    last_error: CriterionCheckError | None = None
    while time.monotonic() < deadline:
        try:
            children = await self._pull_children(context)
            self._check_graph_shape(children)
            self._check_children_completed(children)
            artifact_children = await self._artifact_children(children)
            self._check_children_completed(artifact_children)
            probes = await self._pull_probe_results(context, artifact_children)
            self._check_probes_succeeded(probes, artifact_children)
            return children, artifact_children, probes
        except CriterionCheckError as err:
            last_error = err
            await asyncio.sleep(interval_s)
    raise CriterionCheckError(f"timed out waiting for smoke child artifacts: {last_error}")
```

Then `evaluate` should call this helper before `_verify_env_content`.

- [ ] **Step 4: If local evidence points elsewhere, do not apply the smoke-worker change**

If Task 3 identifies dispatch wiring or child payload failure instead, fix the responsible production file and keep the smoke fixture waiting semantics unchanged until the integration test proves otherwise.

## Task 5: Verify Locally Before Pushing

- [ ] **Step 1: Run focused Python checks**

```bash
uv run ruff check ergon_core/ergon_core/core/application/jobs/worker_execute.py ergon_core/ergon_core/core/application/tasks/management.py tests/fixtures/smoke_components/smoke_base/worker_base.py tests/fixtures/smoke_components/smoke_base/recursive.py tests/fixtures/smoke_components/smoke_base/criterion_base.py
uv run ruff format --check ergon_core/ergon_core/core/application/jobs/worker_execute.py ergon_core/ergon_core/core/application/tasks/management.py tests/fixtures/smoke_components/smoke_base/worker_base.py tests/fixtures/smoke_components/smoke_base/recursive.py tests/fixtures/smoke_components/smoke_base/criterion_base.py
uv run ty check ergon_core/ergon_core/core/application/jobs/worker_execute.py ergon_core/ergon_core/core/application/tasks/management.py
```

Expected: all pass.

- [ ] **Step 2: Run focused unit and integration tests**

```bash
uv run pytest ergon_core/tests/unit/core/application/jobs/test_worker_execute_live_sandbox_attach.py ergon_core/tests/unit/runtime/test_child_function_payloads.py -v
uv run pytest ergon_core/tests/unit/runtime/test_smoke_topology_drift.py ergon_core/tests/unit/architecture/test_smoke_fixture_package_boundary.py -v
uv run pytest ergon_core/tests/integration/runtime/test_dynamic_task_propagation.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 3: Run all three local smokes with one cohort member**

```bash
scripts/smoke_local_run.sh swebench-verified 1
scripts/smoke_local_run.sh minif2f 1
scripts/smoke_local_run.sh researchrubrics 1
```

Expected: all pass end to end.

- [ ] **Step 4: Run all three local smokes with CI-sized cohorts**

```bash
scripts/smoke_local_run.sh swebench-verified 3
scripts/smoke_local_run.sh minif2f 3
scripts/smoke_local_run.sh researchrubrics 3
```

Expected: all pass end to end. This is the gate before pushing.

## Task 6: Commit, Push, Then Use CI Only As Confirmation

- [ ] **Step 1: Commit the tested fix and coverage**

```bash
git status --short
git add ergon_core tests docs/superpowers/plans/2026-05-18-pr11-local-smoke-debugging-and-coverage.md
git commit -m "Cover dynamic task propagation in PR11 smokes"
```

- [ ] **Step 2: Push once local smokes are green**

```bash
git push
```

- [ ] **Step 3: Poll CI only after local green**

```bash
gh pr checks 65 --watch
```

Expected: CI confirms the local result. If CI disagrees, compare CI logs to local logs before changing code.

## Done Definition

- Local integration coverage fails on the old propagation behavior and passes after the fix.
- Local `swebench-verified`, `minif2f`, and `researchrubrics` smokes pass with cohort size 3.
- Fast CI remains green.
- Smoke CI is used only as final confirmation, not as the primary debugger.
