import assert from "node:assert/strict";
import test from "node:test";

import { hydrateRunSnapshot } from "@/lib/run-state";
import { applySandboxCommand, applySandboxCreated, applyTaskStatusChanged } from "@/lib/run-state/reducers";
import { TaskStatus } from "@/lib/types";
import { createDashboardSeed, FIXTURE_IDS } from "../../tests/helpers/dashboardFixtures";
import { shouldRequestSocketSnapshot } from "./useRunState";

test("does not request socket full-state snapshot when REST or SSR state is already hydrated", () => {
  assert.equal(shouldRequestSocketSnapshot(true), false);
});

test("requests socket full-state snapshot when no REST or SSR state is available yet", () => {
  assert.equal(shouldRequestSocketSnapshot(false), true);
});

test("task status reducer records transition history", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const state = hydrateRunSnapshot(run);
  const next = applyTaskStatusChanged(state, {
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    status: TaskStatus.COMPLETED,
    timestamp: "2026-03-18T12:01:00.000Z",
    assignedWorkerId: null,
    assignedWorkerSlug: null,
  });

  const task = next.tasks.get(FIXTURE_IDS.solveTaskId);
  assert.equal(task?.status, TaskStatus.COMPLETED);
  assert.equal(task?.history?.at(-1)?.to, TaskStatus.COMPLETED);
});

test("sandbox command before sandbox creation is preserved", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const command = {
    command: "python solve.py",
    stdout: "ok",
    stderr: null,
    exitCode: 0,
    durationMs: 123,
    timestamp: "2026-03-18T12:00:05.000Z",
  };
  const state = hydrateRunSnapshot({
    ...run,
    sandboxesByTask: {},
  });
  const commandFirst = applySandboxCommand(state, FIXTURE_IDS.solveTaskId, command);
  assert.equal(commandFirst.sandboxesByTask.get(FIXTURE_IDS.solveTaskId), undefined);

  const withSandbox = applySandboxCreated(
    commandFirst,
    {
      sandboxId: "sandbox-1",
      taskId: FIXTURE_IDS.solveTaskId,
      template: null,
      timeoutMinutes: 10,
      status: "active",
      createdAt: "2026-03-18T12:00:06.000Z",
      closedAt: null,
      closeReason: null,
      commands: [],
    },
    [command],
  );

  assert.deepEqual(withSandbox.sandboxesByTask.get(FIXTURE_IDS.solveTaskId)?.commands, [command]);
});

test("sandbox creation deduplicates commands already present in the created sandbox", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const command = {
    command: "python solve.py",
    stdout: "ok",
    stderr: null,
    exitCode: 0,
    durationMs: 123,
    timestamp: "2026-03-18T12:00:05.000Z",
  };
  const state = hydrateRunSnapshot({ ...run, sandboxesByTask: {} });
  const withSandbox = applySandboxCreated(
    state,
    {
      sandboxId: "sandbox-1",
      taskId: FIXTURE_IDS.solveTaskId,
      template: null,
      timeoutMinutes: 10,
      status: "active",
      createdAt: "2026-03-18T12:00:06.000Z",
      closedAt: null,
      closeReason: null,
      commands: [command],
    },
    [command],
  );

  assert.deepEqual(withSandbox.sandboxesByTask.get(FIXTURE_IDS.solveTaskId)?.commands, [command]);
});

test("cancelled task status records terminal task and execution timestamps", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const running = applyTaskStatusChanged(hydrateRunSnapshot(run), {
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    status: TaskStatus.RUNNING,
    timestamp: "2026-03-18T12:00:10.000Z",
    assignedWorkerId: null,
    assignedWorkerSlug: null,
  });
  const cancelled = applyTaskStatusChanged(running, {
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    status: TaskStatus.CANCELLED,
    timestamp: "2026-03-18T12:00:20.000Z",
    assignedWorkerId: null,
    assignedWorkerSlug: null,
  });

  const task = cancelled.tasks.get(FIXTURE_IDS.solveTaskId);
  const execution = cancelled.executionsByTask.get(FIXTURE_IDS.solveTaskId)?.at(-1);
  assert.equal(task?.completedAt, "2026-03-18T12:00:20.000Z");
  assert.equal(execution?.completedAt, "2026-03-18T12:00:20.000Z");
  assert.equal(cancelled.cancelledTasks, 1);
});
