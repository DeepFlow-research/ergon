import assert from "node:assert/strict";
import test from "node:test";

import {
  parseDashboardWorkflowStartedData,
  parseTaskStatusSocketData,
} from "../../src/lib/contracts/events";
import { parseCohortDetail, parseRunSnapshot } from "../../src/lib/contracts/rest";
import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";

test("run snapshot parser accepts object-map transport", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const parsed = parseRunSnapshot(run);

  assert.equal(parsed.id, FIXTURE_IDS.runId);
  assert.deepEqual(Object.keys(parsed.tasks ?? {}).sort(), [
    FIXTURE_IDS.exploreTaskId,
    FIXTURE_IDS.rootTaskId,
    FIXTURE_IDS.solveTaskId,
  ]);
});

test("run snapshot parser rejects legacy tuple-map transport", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const legacyPayload = {
    ...run,
    tasks: Object.entries(run.tasks ?? {}),
  };

  assert.throws(() => parseRunSnapshot(legacyPayload));
});

test("cohort detail parser accepts harness payload", () => {
  const seed = createDashboardSeed();
  const cohortDetail = seed.cohortDetails?.[FIXTURE_IDS.cohortId];

  assert.ok(cohortDetail);
  const parsed = parseCohortDetail(cohortDetail);

  assert.equal(parsed.summary.cohort_id, FIXTURE_IDS.cohortId);
  assert.equal((parsed.runs ?? []).length, 1);
});

test("workflow started event parser validates recursive task trees", () => {
  const payload = {
    run_id: FIXTURE_IDS.runId,
    experiment_id: FIXTURE_IDS.experimentId,
    workflow_name: "parallel",
    started_at: "2026-03-18T12:00:00.000Z",
    total_tasks: 2,
    total_leaf_tasks: 1,
    task_tree: {
      id: "123e4567-e89b-42d3-a456-426614174000",
      name: "Root",
      description: "Root task",
      assigned_to: {
        id: FIXTURE_IDS.workerId,
        name: "planner",
        type: "MockWorker",
      },
      full_team: null,
      children: [
        {
          id: "123e4567-e89b-42d3-a456-426614174001",
          name: "Leaf",
          description: "Leaf task",
          assigned_to: {
            id: FIXTURE_IDS.workerId,
            name: "planner",
            type: "MockWorker",
          },
          full_team: null,
          children: [],
          depends_on: [],
          parent_id: "123e4567-e89b-42d3-a456-426614174000",
          is_leaf: true,
          resources: [],
          evaluator: null,
          evaluator_type: null,
        },
      ],
      depends_on: [],
      parent_id: null,
      is_leaf: false,
      resources: [],
      evaluator: null,
      evaluator_type: null,
    },
  };

  const parsed = parseDashboardWorkflowStartedData(payload);

  assert.equal(parsed.task_tree.children[0]?.name, "Leaf");
});

test("socket task status parser rejects malformed payloads", () => {
  assert.throws(() =>
    parseTaskStatusSocketData({
      runId: FIXTURE_IDS.runId,
      taskId: FIXTURE_IDS.solveTaskId,
      timestamp: "2026-03-18T12:00:14.000Z",
      assignedWorkerId: FIXTURE_IDS.workerId,
      assignedWorkerName: "react-worker",
    }),
  );
});
