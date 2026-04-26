import assert from "node:assert/strict";
import test from "node:test";

import {
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardThreadMessageCreatedData,
  parseDashboardWorkflowStartedData,
  parseTaskStatusSocketData,
} from "../../src/lib/contracts/events";
import { parseCohortDetail, parseRunSnapshot } from "../../src/lib/contracts/rest";
import { deserializeRunState } from "../../src/lib/runState";
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

test("run snapshot hydration preserves context event actions", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const state = deserializeRunState(run);
  const events = state.contextEventsByTask.get(FIXTURE_IDS.solveTaskId) ?? [];

  assert.equal(events.length, 2);
  assert.equal(events[0]?.eventType, "tool_call");
  assert.deepEqual(events[0]?.payload, {
    event_type: "tool_call",
    tool_call_id: "call-lean-check",
    tool_name: "lean_check",
    args: { file: "proof.lean" },
    turn_id: "turn-1",
    turn_token_ids: [101, 102, 103],
    turn_logprobs: null,
  });
});

test("run snapshot hydration orders context events across retried executions", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const first = run.contextEventsByTask?.[FIXTURE_IDS.solveTaskId]?.[0];
  assert.ok(first);
  const retryEvent = {
    ...first,
    id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    taskExecutionId: "execution-solve-2",
    sequence: 0,
    createdAt: "2026-03-18T12:00:30.000Z",
    payload: {
      ...first.payload,
      tool_call_id: "call-retry",
      tool_name: "retry_check",
    },
  };

  const state = deserializeRunState({
    ...run,
    contextEventsByTask: {
      [FIXTURE_IDS.solveTaskId]: [retryEvent, first],
    },
  });
  const events = state.contextEventsByTask.get(FIXTURE_IDS.solveTaskId) ?? [];

  assert.equal(events[0]?.id, first.id);
  assert.equal(events[1]?.id, retryEvent.id);
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
  assert.equal((parsed.runs ?? []).length, 3);
  assert.equal(parsed.runs[0]?.total_tasks, 10);
  assert.equal(parsed.runs[0]?.total_cost_usd, 0.12);
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

test("dashboard nested DTO event parser accepts backend snake-case payloads", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];
  const thread = run?.threads?.[0];
  const message = thread?.messages?.[0];
  const evaluation = run?.evaluationsByTask?.[FIXTURE_IDS.solveTaskId];

  assert.ok(thread);
  assert.ok(message);
  assert.ok(evaluation);

  const parsedThread = parseDashboardThreadMessageCreatedData({
    run_id: FIXTURE_IDS.runId,
    thread: {
      id: thread.id,
      run_id: thread.runId,
      task_id: thread.taskId,
      topic: thread.topic,
      summary: "Leaf workers report completion artifacts and probe exit status.",
      agent_a_id: thread.agentAId,
      agent_b_id: thread.agentBId,
      created_at: thread.createdAt,
      updated_at: thread.updatedAt,
      messages: [],
    },
    message: {
      id: message.id,
      thread_id: message.threadId,
      thread_topic: message.threadTopic,
      run_id: message.runId,
      task_id: message.taskId,
      from_agent_id: message.fromAgentId,
      to_agent_id: message.toAgentId,
      content: message.content,
      sequence_num: message.sequenceNum,
      created_at: message.createdAt,
    },
  });

  assert.equal(
    parsedThread.thread.summary,
    "Leaf workers report completion artifacts and probe exit status.",
  );

  const parsedEvaluation = parseDashboardTaskEvaluationUpdatedData({
    run_id: FIXTURE_IDS.runId,
    task_id: FIXTURE_IDS.solveTaskId,
    evaluation: {
      id: evaluation.id,
      run_id: evaluation.runId,
      task_id: evaluation.taskId,
      total_score: evaluation.totalScore,
      max_score: evaluation.maxScore,
      normalized_score: evaluation.normalizedScore,
      stages_evaluated: evaluation.stagesEvaluated,
      stages_passed: evaluation.stagesPassed,
      failed_gate: evaluation.failedGate,
      created_at: evaluation.createdAt,
      criterion_results: [],
    },
  });

  assert.equal(parsedThread.message.sequenceNum, message.sequenceNum);
  assert.equal(parsedEvaluation.evaluation.totalScore, evaluation.totalScore);
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
