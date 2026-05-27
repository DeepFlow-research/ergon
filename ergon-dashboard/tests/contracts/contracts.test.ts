import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  dashboardEventSchemas,
  isDashboardSampleRuntimeGraphEvent,
  parseDashboardContextEventData,
  parseDashboardSampleRuntimeEventData,
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardThreadMessageCreatedData,
  parseDashboardWorkflowStartedData,
  parseTaskStatusSocketData,
} from "../../src/lib/contracts/events";
import { parseSampleSnapshot } from "../../src/lib/contracts/rest";
import { deserializeSampleState } from "../../src/lib/sampleState";
import { store } from "../../src/lib/state/store";
import {
  getHarnessSample,
  resetDashboardHarness,
  seedDashboardHarness,
} from "../../src/lib/testing/dashboardHarness";
import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";

test("run snapshot parser accepts object-map transport", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const parsed = parseSampleSnapshot(run);

  assert.equal(parsed.id, FIXTURE_IDS.sampleId);
  assert.deepEqual(Object.keys(parsed.tasks ?? {}).sort(), [
    FIXTURE_IDS.exploreTaskId,
    FIXTURE_IDS.rootTaskId,
    FIXTURE_IDS.solveTaskId,
  ]);
});

test("run snapshot hydration converts context part chunks into UI action payloads", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const state = deserializeSampleState(run);
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
    taskExecutionId: "99999999-9999-4999-8999-999999999998",
    sequence: 0,
    createdAt: "2026-03-18T12:00:30.000Z",
    payload: {
      ...first.payload,
      part: {
        ...first.payload.part,
        tool_call_id: "call-retry",
        tool_name: "retry_check",
      },
    },
  };

  const state = deserializeSampleState({
    ...run,
    contextEventsByTask: {
      [FIXTURE_IDS.solveTaskId]: [retryEvent, first],
    },
  });
  const events = state.contextEventsByTask.get(FIXTURE_IDS.solveTaskId) ?? [];

  assert.equal(events[0]?.id, first.id);
  assert.equal(events[1]?.id, retryEvent.id);
});

test("run snapshot parser rejects tuple-map transport", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];

  assert.ok(run);
  const legacyPayload = {
    ...run,
    tasks: Object.entries(run.tasks ?? {}),
  };

  assert.throws(() => parseSampleSnapshot(legacyPayload));
});

test("dashboard harness only serves explicitly seeded runs", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];
  assert.ok(run);

  resetDashboardHarness();
  store.seedSample(deserializeSampleState({ ...run, id: "live-event-run" }));

  assert.equal(getHarnessSample("live-event-run"), null);

  seedDashboardHarness({ runs: [run] });

  const seededRun = getHarnessSample(FIXTURE_IDS.sampleId);
  assert.equal(seededRun?.id, FIXTURE_IDS.sampleId);
  assert.equal(deserializeSampleState(seededRun).id, FIXTURE_IDS.sampleId);
});

test("workflow started event parser validates run snapshots", () => {
  const seed = createDashboardSeed();
  const run = seed.runs?.[0];
  assert.ok(run);

  const payload = {
    sample_id: FIXTURE_IDS.sampleId,
    workflow_name: "parallel",
    started_at: "2026-03-18T12:00:00.000Z",
    total_tasks: run.totalTasks,
    total_leaf_tasks: run.totalLeafTasks,
    snapshot: run,
  };

  const parsed = parseDashboardWorkflowStartedData(payload);

  assert.equal(parsed.snapshot.tasks[FIXTURE_IDS.solveTaskId]?.name, "Write proof");
});

test("generated dashboard event schemas cover graph and context live events", () => {
  assert.ok(dashboardEventSchemas["dashboard/sample.runtime_event"]);
  assert.ok(dashboardEventSchemas["dashboard/context.event"]);
});

test("frontend routes expose experiment grouping and no cohort surface", () => {
  const root = process.cwd();

  assert.equal(fs.existsSync(path.join(root, "src/app/experiments/[experimentId]/page.tsx")), true);
  assert.equal(fs.existsSync(path.join(root, "src/app/cohorts/page.tsx")), false);
  assert.equal(fs.existsSync(path.join(root, "src/app/api/cohorts/route.ts")), false);
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
    sample_id: FIXTURE_IDS.sampleId,
    thread: {
      id: thread.id,
      sample_id: thread.sampleId,
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
      sample_id: message.sampleId,
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
    sample_id: FIXTURE_IDS.sampleId,
    task_id: FIXTURE_IDS.solveTaskNodeUuid,
    evaluation: {
      id: evaluation.id,
      sample_id: evaluation.sampleId,
      task_id: evaluation.taskId,
      evaluator_name: evaluation.evaluatorName,
      aggregation_rule: evaluation.aggregationRule,
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

test("dashboard sample runtime event parser accepts backend wrapped event", () => {
  const parsed = parseDashboardSampleRuntimeEventData({
    mutation: {
      id: "77777777-7777-4777-8777-777777777777",
      sample_id: FIXTURE_IDS.sampleId,
      sequence: 4,
      mutation_type: "node.added",
      target_type: "node",
      target_id: FIXTURE_IDS.solveTaskNodeUuid,
      actor: "system",
      old_value: null,
      new_value: {
        task_slug: "child",
        status: "pending",
      },
      reason: "planned subtask",
      created_at: "2026-03-18T12:00:14.000000Z",
    },
  });

  assert.equal(parsed.sample_id, FIXTURE_IDS.sampleId);
  assert.equal(parsed.sequence, 4);
  assert.equal(parsed.target_id, FIXTURE_IDS.solveTaskNodeUuid);
  assert.equal(parsed.created_at, "2026-03-18T12:00:14.000000Z");
});

test("dashboard sample runtime event parser preserves canonical edge task ids", () => {
  const parsed = parseDashboardSampleRuntimeEventData({
    mutation: {
      id: "77777777-7777-4777-8777-777777777777",
      sample_id: FIXTURE_IDS.sampleId,
      sequence: 5,
      mutation_type: "edge.added",
      target_type: "edge",
      target_id: "99999999-9999-4999-8999-999999999999",
      actor: "system",
      old_value: null,
      new_value: {
        mutation_type: "edge.added",
        source_task_id: FIXTURE_IDS.rootTaskId,
        target_task_id: FIXTURE_IDS.solveTaskId,
        status: "pending",
      },
      reason: "parent-child",
      created_at: "2026-03-18T12:00:14.000000Z",
    },
  });

  assert.equal(parsed.new_value.source_task_id, FIXTURE_IDS.rootTaskId);
  assert.equal(parsed.new_value.target_task_id, FIXTURE_IDS.solveTaskId);
  assert.equal("source_node_id" in parsed.new_value, false);
  assert.equal("target_node_id" in parsed.new_value, false);
});

test("dashboard sample runtime graph guard ignores component-only WAL events", () => {
  assert.equal(
    isDashboardSampleRuntimeGraphEvent({
      event: {
        eventId: "77777777-7777-4777-8777-777777777777",
        sampleId: FIXTURE_IDS.sampleId,
        timestamp: "2026-03-18T12:00:14.000000Z",
        eventType: "worker.added",
        targetType: "task",
        targetId: FIXTURE_IDS.solveTaskNodeUuid,
        workerSlug: "minif2f-smoke-worker",
        workerType: "tests.fixtures.smoke_components.workers:Worker",
        modelTarget: "openai:gpt-4o",
        worker: {},
        payload: {},
      },
    }),
    false,
  );
});

test("dashboard sample runtime graph guard ignores sample lifecycle WAL events", () => {
  assert.equal(
    isDashboardSampleRuntimeGraphEvent({
      event: {
        eventId: "77777777-7777-4777-8777-777777777777",
        sampleId: FIXTURE_IDS.sampleId,
        timestamp: "2026-03-18T12:00:14.000000Z",
        eventType: "sample.status_changed",
        targetType: "sample",
        targetId: FIXTURE_IDS.sampleId,
        status: "completed",
        payload: { reason: "workflow completed" },
      },
    }),
    false,
  );
});

test("dashboard sample runtime event parser projects typed task events into graph mutations", () => {
  const parsed = parseDashboardSampleRuntimeEventData({
    event: {
      eventId: "77777777-7777-4777-8777-777777777777",
      sampleId: FIXTURE_IDS.sampleId,
      timestamp: "2026-03-18T12:00:14.000000Z",
      eventType: "task.added",
      targetType: "task",
      targetId: FIXTURE_IDS.solveTaskNodeUuid,
      taskSlug: "solve",
      status: "pending",
      task: {
        instance_key: "proof-1",
        description: "Write the proof.",
      },
      payload: {
        worker_slug: "minif2f-smoke-worker",
      },
    },
  });

  assert.equal(parsed.mutation_type, "node.added");
  assert.equal(parsed.target_type, "node");
  assert.deepEqual(parsed.new_value, {
    task_slug: "solve",
    instance_key: "proof-1",
    description: "Write the proof.",
    status: "pending",
    assigned_worker_slug: "minif2f-smoke-worker",
  });
});

test("dashboard sample runtime event parser projects typed edge events into graph mutations", () => {
  const parsed = parseDashboardSampleRuntimeEventData({
    event: {
      eventId: "77777777-7777-4777-8777-777777777777",
      sampleId: FIXTURE_IDS.sampleId,
      timestamp: "2026-03-18T12:00:14.000000Z",
      eventType: "edge.added",
      targetType: "edge",
      targetId: "99999999-9999-4999-8999-999999999999",
      sourceTaskId: FIXTURE_IDS.actionId,
      targetTaskId: FIXTURE_IDS.solveTaskNodeUuid,
      status: "pending",
      payload: {},
    },
  });

  assert.equal(parsed.mutation_type, "edge.added");
  assert.deepEqual(parsed.new_value, {
    mutation_type: "edge.added",
    source_task_id: FIXTURE_IDS.actionId,
    target_task_id: FIXTURE_IDS.solveTaskNodeUuid,
    status: "pending",
  });
});

test("dashboard sample runtime event parser treats annotation updates as sets", () => {
  const parsed = parseDashboardSampleRuntimeEventData({
    event: {
      eventId: "77777777-7777-4777-8777-777777777777",
      sampleId: FIXTURE_IDS.sampleId,
      timestamp: "2026-03-18T12:00:14.000000Z",
      eventType: "annotation.updated",
      targetType: "task",
      targetId: FIXTURE_IDS.solveTaskNodeUuid,
      key: "review",
      value: {
        namespace: "review",
        payload: { label: "important" },
      },
      payload: {},
    },
  });

  assert.equal(parsed.mutation_type, "annotation.set");
  assert.deepEqual(parsed.new_value, {
    namespace: "review",
    payload: { label: "important" },
  });
});

test("dashboard context event parser accepts backend context part payloads", () => {
  const parsed = parseDashboardContextEventData({
    id: "88888888-8888-4888-8888-888888888888",
    sample_id: FIXTURE_IDS.sampleId,
    task_execution_id: "99999999-9999-4999-8999-999999999999",
    task_id: FIXTURE_IDS.solveTaskNodeUuid,
    worker_binding_key: "swebench-smoke-worker",
    sequence: 0,
    event_type: "assistant_text",
    payload: {
      part: {
        part_kind: "assistant_text",
        content: "planning subtasks",
      },
      token_ids: null,
      logprobs: null,
      sequence: 0,
      worker_binding_key: "swebench-smoke-worker",
      turn_id: "turn-1",
      started_at: "2026-03-18T12:00:14.000000Z",
      completed_at: "2026-03-18T12:00:14.000000Z",
      policy_version: null,
    },
    created_at: "2026-03-18T12:00:14.000000Z",
    started_at: "2026-03-18T12:00:14.000000Z",
    completed_at: "2026-03-18T12:00:14.000000Z",
  });

  assert.deepEqual(parsed.payload, {
    event_type: "assistant_text",
    text: "planning subtasks",
    turn_id: "turn-1",
    turn_token_ids: null,
    turn_logprobs: null,
  });
});

test("socket task status parser rejects malformed payloads", () => {
  assert.throws(() =>
    parseTaskStatusSocketData({
      sampleId: FIXTURE_IDS.sampleId,
      taskId: FIXTURE_IDS.solveTaskId,
      timestamp: "2026-03-18T12:00:14.000Z",
      assignedWorkerId: FIXTURE_IDS.workerId,
      assignedWorkerSlug: "react-worker",
    }),
  );
});
