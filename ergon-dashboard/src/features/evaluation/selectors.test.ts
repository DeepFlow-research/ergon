import assert from "node:assert/strict";
import test from "node:test";

import type { TaskEvaluationState, TaskState, WorkflowRunState } from "@/lib/types";
import { TaskStatus } from "@/lib/types";
import {
  buildContainerEvaluationRollup,
  combineEvaluationStatuses,
  evaluationToRollup,
  isEvaluationBearingTask,
} from "./selectors";

function task(id: string, childIds: string[] = []): TaskState {
  return {
    id,
    name: id,
    description: id,
    status: TaskStatus.COMPLETED,
    parentId: null,
    childIds,
    dependsOnIds: [],
    isLeaf: childIds.length === 0,
    level: 0,
    assignedWorkerId: null,
    assignedWorkerName: null,
    startedAt: null,
    completedAt: null,
    history: [],
    lastTrigger: null,
  };
}

function evaluation(taskId: string, statuses: Array<"passed" | "failed" | "errored" | "skipped">): TaskEvaluationState {
  return {
    id: `evaluation-${taskId}`,
    runId: "run-1",
    taskId,
    evaluatorName: "rubric",
    aggregationRule: "weighted_sum",
    totalScore: statuses.filter((status) => status === "passed").length,
    maxScore: statuses.length,
    normalizedScore: statuses.length > 0 ? statuses.filter((status) => status === "passed").length / statuses.length : 0,
    stagesEvaluated: 1,
    stagesPassed: statuses.every((status) => status === "passed") ? 1 : 0,
    failedGate: null,
    createdAt: "2026-04-27T12:00:00.000Z",
    criterionResults: statuses.map((status, index) => ({
      id: `${taskId}-${index}`,
      stageNum: 0,
      stageName: "default",
      criterionNum: index,
      criterionType: "fixture",
      criterionDescription: `${status} criterion`,
      criterionName: `${status} criterion`,
      status,
      passed: status === "passed",
      weight: 1,
      contribution: status === "passed" ? 1 : 0,
      score: status === "passed" ? 1 : 0,
      maxScore: 1,
      feedback: null,
      modelReasoning: null,
      skippedReason: null,
      evaluationInput: null,
      error: status === "errored" ? { kind: "fixture" } : null,
      evaluatedActionIds: [],
      evaluatedResourceIds: [],
    })),
  };
}

function state(evaluationsByTask: Map<string, TaskEvaluationState>): WorkflowRunState {
  return {
    id: "run-1",
    experimentId: "experiment-1",
    name: "run",
    status: "completed",
    tasks: new Map([
      ["root", task("root", ["child-a", "child-b"])],
      ["child-a", task("child-a")],
      ["child-b", task("child-b")],
    ]),
    rootTaskId: "root",
    resourcesByTask: new Map(),
    executionsByTask: new Map(),
    evaluationsByTask,
    sandboxesByTask: new Map(),
    threads: [],
    contextEventsByTask: new Map(),
    startedAt: "2026-04-27T12:00:00.000Z",
    completedAt: null,
    durationSeconds: null,
    totalTasks: 3,
    totalLeafTasks: 2,
    completedTasks: 3,
    failedTasks: 0,
    runningTasks: 0,
    cancelledTasks: 0,
    finalScore: null,
    error: null,
    edges: new Map(),
    annotationsByTarget: new Map(),
    unhandledMutations: [],
  };
}

test("evaluationToRollup returns null when there are no criteria", () => {
  assert.equal(evaluationToRollup(evaluation("child-a", [])), null);
});

test("evaluationToRollup preserves explicit failed, skipped, and errored states", () => {
  const rollup = evaluationToRollup(evaluation("child-a", ["passed", "failed", "skipped"]));

  assert.equal(rollup?.status, "failing");
  assert.equal(rollup?.passed, 1);
  assert.equal(rollup?.failed, 1);
  assert.equal(rollup?.skipped, 1);
  assert.deepEqual(rollup?.criterionStatuses, ["passed", "failed", "skipped"]);

  assert.equal(evaluationToRollup(evaluation("child-a", ["errored"]))?.status, "errored");
});

test("container rollup aggregates descendants and returns null for no evidence", () => {
  const empty = state(new Map());
  assert.equal(buildContainerEvaluationRollup(empty, "root"), null);
  assert.equal(isEvaluationBearingTask(empty, "root"), false);

  const populated = state(
    new Map([
      ["child-a", evaluation("child-a", ["passed", "skipped"])],
      ["child-b", evaluation("child-b", ["passed"])],
    ]),
  );

  const rollup = buildContainerEvaluationRollup(populated, "root");

  assert.equal(rollup?.status, "mixed");
  assert.equal(rollup?.totalCriteria, 3);
  assert.equal(rollup?.passed, 2);
  assert.equal(rollup?.skipped, 1);
  assert.deepEqual(rollup?.attachedTaskIds, ["child-a", "child-b"]);
  assert.equal(isEvaluationBearingTask(populated, "root"), true);
});

test("combineEvaluationStatuses prioritizes errored then failing before mixed", () => {
  assert.equal(combineEvaluationStatuses(["passing", "errored", "failing"]), "errored");
  assert.equal(combineEvaluationStatuses(["passing", "failing", "mixed"]), "failing");
  assert.equal(combineEvaluationStatuses(["passing", "skipped"]), "mixed");
  assert.equal(combineEvaluationStatuses(["skipped", "skipped"]), "skipped");
});
