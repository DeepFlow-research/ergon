import assert from "node:assert/strict";
import test from "node:test";

import fixture from "../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { parseGraphMutationDtoArray } from "@/features/graph/contracts/graphMutations";
import type { RunEvent } from "@/lib/runEvents";
import { buildRunEvents } from "@/lib/runEvents";
import { deserializeRunState } from "@/lib/runState";
import { TaskStatus, TaskTrigger } from "@/lib/types";
import { buildRunActivities } from "./buildRunActivities";
import { resolveActivitySnapshotSequence } from "./snapshotSequence";

test("buildRunActivities surfaces semantic activity kinds without creating actor lanes", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const noisyTaskId = "10000000-0000-4000-8000-000000000002";
  runState.sandboxesByTask.set(noisyTaskId, {
    sandboxId: "sandbox-noisy",
    taskId: noisyTaskId,
    template: "python",
    timeoutMinutes: 30,
    status: "closed",
    createdAt: "2025-01-01T00:00:05.000Z",
    closedAt: "2025-01-01T00:00:20.000Z",
    closeReason: "completed",
    commands: [
      {
        command: "pnpm test --verbose",
        stdout: null,
        stderr: null,
        exitCode: 0,
        durationMs: 1000,
        timestamp: "2025-01-01T00:00:10.000Z",
      },
    ],
  });
  runState.executionsByTask.set(noisyTaskId, [
    {
      id: "execution-noisy",
      taskId: noisyTaskId,
      attemptNumber: 1,
      status: TaskStatus.COMPLETED,
      agentId: "agent-a",
      agentName: "worker-1",
      startedAt: "2025-01-01T00:00:04.000Z",
      completedAt: "2025-01-01T00:00:16.000Z",
      finalAssistantMessage: null,
      outputResourceIds: [],
      errorMessage: null,
      score: null,
      evaluationDetails: {},
    },
  ]);
  runState.contextEventsByTask.set(noisyTaskId, [
    {
      id: "context-noisy",
      taskExecutionId: "execution-noisy",
      taskNodeId: noisyTaskId,
      workerBindingKey: "worker-1",
      sequence: 12,
      eventType: "tool_call",
      payload: {
        event_type: "tool_call",
        tool_call_id: "tool-call-noisy",
        tool_name: "shell",
        args: { command: "pnpm test" },
        turn_id: "turn-noisy",
        turn_token_ids: null,
        turn_logprobs: null,
      },
      createdAt: "2025-01-01T00:00:12.000Z",
      startedAt: "2025-01-01T00:00:12.000Z",
      completedAt: "2025-01-01T00:00:13.000Z",
    },
  ]);
  runState.threads = [
    ...runState.threads,
    {
      id: "thread-noisy",
      runId: runState.id,
      taskId: noisyTaskId,
      topic: "coordination",
      agentAId: "agent-a",
      agentBId: "agent-b",
      createdAt: "2025-01-01T00:00:12.000Z",
      updatedAt: "2025-01-01T00:00:12.000Z",
      messages: [
        {
          id: "message-noisy",
          threadId: "thread-noisy",
          threadTopic: "coordination",
          runId: runState.id,
          taskId: noisyTaskId,
          taskExecutionId: null,
          fromAgentId: "agent-a",
          toAgentId: "agent-b",
          content: "Verbose coordination message",
          sequenceNum: 99,
          createdAt: "2025-01-01T00:00:12.000Z",
        },
      ],
    },
  ];
  const markerEvents: RunEvent[] = [
    {
      id: "marker-workflow-started",
      kind: "workflow.started",
      at: "2025-01-01T00:00:06.000Z",
      runName: "Marker workflow",
    },
    {
      id: "marker-workflow-completed",
      kind: "workflow.completed",
      at: "2025-01-01T00:00:07.000Z",
      status: "completed",
      finalScore: 1,
      error: null,
    },
    {
      id: "marker-task-transition",
      kind: "task.transition",
      at: "2025-01-01T00:00:08.000Z",
      taskId: noisyTaskId,
      taskName: "Noisy task",
      from: TaskStatus.READY,
      to: TaskStatus.RUNNING,
      trigger: TaskTrigger.WORKER_STARTED,
      reason: null,
      actor: "worker-1",
    },
    {
      id: "marker-thread-message",
      kind: "thread.message",
      at: "2025-01-01T00:00:09.000Z",
      taskId: noisyTaskId,
      threadId: "thread-noisy",
      authorRole: "agent",
      preview: "Marker message",
    },
    {
      id: "marker-task-evaluation",
      kind: "task.evaluation",
      at: "2025-01-01T00:00:11.000Z",
      taskId: noisyTaskId,
      score: 0.9,
      passed: true,
    },
    {
      id: "marker-resource-published",
      kind: "resource.published",
      at: "2025-01-01T00:00:13.000Z",
      taskId: noisyTaskId,
      name: "artifact.json",
      mimeType: "application/json",
      sizeBytes: 128,
    },
    {
      id: "marker-unhandled-mutation",
      kind: "unhandled.mutation",
      at: "2025-01-01T00:00:14.000Z",
      taskId: noisyTaskId,
      sequence: 13,
      mutationType: "unknown_marker",
      note: "Unhandled marker mutation",
    },
  ];
  const events = [...buildRunEvents(runState), ...markerEvents];

  const activities = buildRunActivities({
    runState,
    events,
    mutations,
    currentSequence: 14,
  });

  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "execution" &&
        activity.taskId === noisyTaskId &&
        activity.isInstant === false,
    ),
  );
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "graph" &&
        activity.sequence === 10 &&
        activity.taskId === "10000000-0000-4000-8000-000000000003",
    ),
  );
  assert.deepEqual(
    [...new Set(activities.map((activity) => String(activity.kind)))].sort(),
    [
      "artifact",
      "context",
      "evaluation",
      "execution",
      "graph",
      "message",
      "sandbox",
    ],
  );
  assert.ok(activities.some((activity) => String(activity.label).includes("pnpm test")));
  assert.ok(activities.some((activity) => String(activity.label).includes("artifact.json")));
  assert.ok(activities.some((activity) => String(activity.label).includes("tool_call")));
  assert.ok(activities.some((activity) => String(activity.label).includes("Marker message")));
  assert.ok(activities.some((activity) => String(activity.label).includes("Evaluation")));
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "execution" &&
        activity.band === "work" &&
        activity.lineage.taskExecutionId === "execution-noisy",
    ),
  );
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "context" &&
        activity.band === "tools" &&
        activity.lineage.taskExecutionId === "execution-noisy",
    ),
  );
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "message" &&
        activity.band === "communication" &&
        activity.lineage.taskId === noisyTaskId,
    ),
  );
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "artifact" &&
        activity.band === "outputs" &&
        activity.lineage.taskId === noisyTaskId,
    ),
  );
  assert.equal(
    activities.some((activity) => "laneId" in activity.metadata),
    false,
  );
});

test("completed trace spans keep full duration when replaying an earlier sequence", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const events = buildRunEvents(runState);

  const activities = buildRunActivities({
    runState,
    events,
    mutations,
    currentSequence: 10,
  });

  const execution = activities.find(
    (activity) => activity.id === "execution:30000000-0000-4000-8000-000000000001",
  );
  const sandbox = activities.find((activity) => activity.id === "sandbox:sandbox-search");
  const graphMarker = activities.find(
    (activity) => activity.kind === "graph" && activity.sequence === 10,
  );

  assert.equal(execution?.startAt, "2026-04-26T12:00:05.000Z");
  assert.equal(execution?.endAt, "2026-04-26T12:00:24.000Z");
  assert.equal(sandbox?.startAt, "2026-04-26T12:00:04.000Z");
  assert.equal(sandbox?.endAt, "2026-04-26T12:00:26.000Z");
  assert.equal(execution?.metadata.openEnded, false);
  assert.equal(sandbox?.metadata.openEnded, false);
  assert.equal(graphMarker?.debug?.source, "graph.mutation");
});

test("context/tool event sequence does not masquerade as graph replay sequence", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const activities = buildRunActivities({
    runState,
    events: buildRunEvents(runState),
    mutations,
    currentSequence: null,
  });

  const toolActivity = activities.find(
    (activity) => activity.id === "context:60000000-0000-4000-8000-000000000001",
  );

  assert.equal(toolActivity?.kind, "context");
  assert.equal(toolActivity?.sequence, null);
  assert.equal(
    toolActivity ? resolveActivitySnapshotSequence(toolActivity, mutations) : null,
    10,
  );
});
