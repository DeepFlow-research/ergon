import type { DashboardHarnessSeedPayload } from "../../src/lib/testing/dashboardHarness";
import type {
  CommunicationThreadState,
  SerializedWorkflowRunState,
  TaskEvaluationState,
  TaskState,
} from "../../src/lib/types";
import { TaskStatus } from "../../src/lib/types";

export const FIXTURE_IDS = {
  cohortId: "11111111-1111-4111-8111-111111111111",
  runId: "22222222-2222-4222-8222-222222222222",
  experimentId: "33333333-3333-4333-8333-333333333333",
  rootTaskId: "task-root",
  exploreTaskId: "task-explore",
  solveTaskId: "task-solve",
  actionId: "44444444-4444-4444-8444-444444444444",
  workerId: "55555555-5555-4555-8555-555555555555",
  threadId: "66666666-6666-4666-8666-666666666666",
  messageIdA: "77777777-7777-4777-8777-777777777777",
  messageIdB: "88888888-8888-4888-8888-888888888888",
  evaluationId: "99999999-9999-4999-8999-999999999999",
  criterionId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
} as const;

function taskState(task: Partial<TaskState> & Pick<TaskState, "id" | "name" | "description" | "status" | "isLeaf" | "level">): TaskState {
  return {
    parentId: null,
    childIds: [],
    dependsOnIds: [],
    assignedWorkerId: FIXTURE_IDS.workerId,
    assignedWorkerName: "react-worker",
    startedAt: "2026-03-18T12:00:00.000Z",
    completedAt: null,
    ...task,
  };
}

function serializedRunState(): SerializedWorkflowRunState {
  const root = taskState({
    id: FIXTURE_IDS.rootTaskId,
    name: "Prove theorem",
    description: "Coordinate the proof strategy across the run.",
    status: TaskStatus.RUNNING,
    isLeaf: false,
    level: 0,
    childIds: [FIXTURE_IDS.exploreTaskId, FIXTURE_IDS.solveTaskId],
    assignedWorkerName: "planner",
  });
  const explore = taskState({
    id: FIXTURE_IDS.exploreTaskId,
    name: "Inspect theorem context",
    description: "Collect promising lemmas and inspect the local proof environment.",
    status: TaskStatus.COMPLETED,
    isLeaf: true,
    level: 1,
    parentId: FIXTURE_IDS.rootTaskId,
    completedAt: "2026-03-18T12:00:12.000Z",
  });
  const solve = taskState({
    id: FIXTURE_IDS.solveTaskId,
    name: "Write proof",
    description: "Draft the Lean proof and validate the produced artifact.",
    status: TaskStatus.RUNNING,
    isLeaf: true,
    level: 1,
    parentId: FIXTURE_IDS.rootTaskId,
    dependsOnIds: [FIXTURE_IDS.exploreTaskId],
  });

  return {
    id: FIXTURE_IDS.runId,
    experimentId: FIXTURE_IDS.experimentId,
    name: "parallel",
    status: "executing",
    tasks: {
      [root.id]: root,
      [explore.id]: explore,
      [solve.id]: solve,
    },
    rootTaskId: FIXTURE_IDS.rootTaskId,
    generationTurnsByTask: {},
    resourcesByTask: {
      [FIXTURE_IDS.solveTaskId]: [
        {
          id: "resource-proof",
          taskId: FIXTURE_IDS.solveTaskId,
          taskExecutionId: "execution-1",
          name: "proof.lean",
          mimeType: "text/plain",
          sizeBytes: 320,
          filePath: "/workspace/proof.lean",
          createdAt: "2026-03-18T12:00:18.000Z",
        },
      ],
    },
    executionsByTask: {
      [FIXTURE_IDS.exploreTaskId]: [
        {
          id: "execution-explore-1",
          taskId: FIXTURE_IDS.exploreTaskId,
          attemptNumber: 1,
          status: TaskStatus.COMPLETED,
          agentId: FIXTURE_IDS.workerId,
          agentName: "planner",
          startedAt: "2026-03-18T12:00:00.000Z",
          completedAt: "2026-03-18T12:00:12.000Z",
          outputText: "Relevant divisibility lemmas identified.",
          outputResourceIds: [],
          errorMessage: null,
          score: null,
          evaluationDetails: {},
        },
      ],
      [FIXTURE_IDS.solveTaskId]: [
        {
          id: "execution-solve-1",
          taskId: FIXTURE_IDS.solveTaskId,
          attemptNumber: 1,
          status: TaskStatus.RUNNING,
          agentId: FIXTURE_IDS.workerId,
          agentName: "react-worker",
          startedAt: "2026-03-18T12:00:14.000Z",
          completedAt: null,
          outputText: null,
          outputResourceIds: ["resource-proof"],
          errorMessage: null,
          score: null,
          evaluationDetails: {},
        },
      ],
    },
    sandboxesByTask: {
      [FIXTURE_IDS.solveTaskId]: {
        sandboxId: "sandbox-1",
        taskId: FIXTURE_IDS.solveTaskId,
        template: "lean4",
        timeoutMinutes: 30,
        status: "active",
        createdAt: "2026-03-18T12:00:10.000Z",
        closedAt: null,
        closeReason: null,
        commands: [
          {
            command: "lake env lean proof.lean",
            stdout: "checking proof...",
            stderr: null,
            exitCode: null,
            durationMs: null,
            timestamp: "2026-03-18T12:00:18.000Z",
          },
        ],
      },
    },
    threads: [
      {
        id: FIXTURE_IDS.threadId,
        runId: FIXTURE_IDS.runId,
        taskId: FIXTURE_IDS.solveTaskId,
        topic: "task_clarification",
        agentAId: `${FIXTURE_IDS.runId}:stakeholder`,
        agentBId: `${FIXTURE_IDS.runId}:worker`,
        createdAt: "2026-03-18T12:00:05.000Z",
        updatedAt: "2026-03-18T12:00:17.000Z",
        messages: [
          {
            id: FIXTURE_IDS.messageIdA,
            threadId: FIXTURE_IDS.threadId,
            runId: FIXTURE_IDS.runId,
            taskId: FIXTURE_IDS.solveTaskId,
            threadTopic: "task_clarification",
            fromAgentId: `${FIXTURE_IDS.runId}:worker`,
            toAgentId: `${FIXTURE_IDS.runId}:stakeholder`,
            content: "Can I use the standard divisibility lemma here?",
            sequenceNum: 0,
            createdAt: "2026-03-18T12:00:05.000Z",
          },
          {
            id: FIXTURE_IDS.messageIdB,
            threadId: FIXTURE_IDS.threadId,
            runId: FIXTURE_IDS.runId,
            taskId: FIXTURE_IDS.solveTaskId,
            threadTopic: "task_clarification",
            fromAgentId: `${FIXTURE_IDS.runId}:stakeholder`,
            toAgentId: `${FIXTURE_IDS.runId}:worker`,
            content: "Yes. Focus on parity first, then discharge the algebraic side condition.",
            sequenceNum: 1,
            createdAt: "2026-03-18T12:00:17.000Z",
          },
        ],
      },
    ],
    evaluationsByTask: {
      [FIXTURE_IDS.solveTaskId]: {
        id: FIXTURE_IDS.evaluationId,
        runId: FIXTURE_IDS.runId,
        taskId: FIXTURE_IDS.solveTaskId,
        totalScore: 0.8,
        maxScore: 1,
        normalizedScore: 0.8,
        stagesEvaluated: 1,
        stagesPassed: 1,
        failedGate: null,
        createdAt: "2026-03-18T12:00:21.000Z",
        criterionResults: [
          {
            id: FIXTURE_IDS.criterionId,
            stageNum: 0,
            stageName: "proof_validation",
            criterionNum: 0,
            criterionType: "code_rule",
            criterionDescription: "Proof compiles and closes all goals",
            score: 0.8,
            maxScore: 1,
            feedback: "Compilation succeeds, but the proof uses a slightly verbose intermediate lemma.",
            evaluationInput: "lake env lean proof.lean",
            error: null,
            evaluatedActionIds: [FIXTURE_IDS.actionId],
            evaluatedResourceIds: ["resource-proof"],
          },
        ],
      },
    },
    startedAt: "2026-03-18T12:00:00.000Z",
    completedAt: null,
    durationSeconds: 24,
    totalTasks: 3,
    totalLeafTasks: 2,
    completedTasks: 1,
    runningTasks: 1,
    failedTasks: 0,
    finalScore: null,
    error: null,
  };
}

export function createDeltaThread(): CommunicationThreadState {
  return {
    id: FIXTURE_IDS.threadId,
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    topic: "task_clarification",
    agentAId: `${FIXTURE_IDS.runId}:stakeholder`,
    agentBId: `${FIXTURE_IDS.runId}:worker`,
    createdAt: "2026-03-18T12:00:05.000Z",
    updatedAt: "2026-03-18T12:00:24.000Z",
    messages: [
      {
        id: FIXTURE_IDS.messageIdA,
        threadId: FIXTURE_IDS.threadId,
        runId: FIXTURE_IDS.runId,
        taskId: FIXTURE_IDS.solveTaskId,
        threadTopic: "task_clarification",
        fromAgentId: `${FIXTURE_IDS.runId}:worker`,
        toAgentId: `${FIXTURE_IDS.runId}:stakeholder`,
        content: "Can I use the standard divisibility lemma here?",
        sequenceNum: 0,
        createdAt: "2026-03-18T12:00:05.000Z",
      },
      {
        id: FIXTURE_IDS.messageIdB,
        threadId: FIXTURE_IDS.threadId,
        runId: FIXTURE_IDS.runId,
        taskId: FIXTURE_IDS.solveTaskId,
        threadTopic: "task_clarification",
        fromAgentId: `${FIXTURE_IDS.runId}:stakeholder`,
        toAgentId: `${FIXTURE_IDS.runId}:worker`,
        content: "Yes. Focus on parity first, then discharge the algebraic side condition.",
        sequenceNum: 1,
        createdAt: "2026-03-18T12:00:17.000Z",
      },
      {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        threadId: FIXTURE_IDS.threadId,
        runId: FIXTURE_IDS.runId,
        taskId: FIXTURE_IDS.solveTaskId,
        threadTopic: "task_clarification",
        fromAgentId: `${FIXTURE_IDS.runId}:worker`,
        toAgentId: `${FIXTURE_IDS.runId}:stakeholder`,
        content: "Understood. I am rewriting the final proof around that parity split now.",
        sequenceNum: 2,
        createdAt: "2026-03-18T12:00:24.000Z",
      },
    ],
  };
}

export function createUpdatedEvaluation(): TaskEvaluationState {
  return {
    id: FIXTURE_IDS.evaluationId,
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    totalScore: 1,
    maxScore: 1,
    normalizedScore: 1,
    stagesEvaluated: 1,
    stagesPassed: 1,
    failedGate: null,
    createdAt: "2026-03-18T12:00:31.000Z",
    criterionResults: [
      {
        id: FIXTURE_IDS.criterionId,
        stageNum: 0,
        stageName: "proof_validation",
        criterionNum: 0,
        criterionType: "code_rule",
        criterionDescription: "Proof compiles and closes all goals",
        score: 1,
        maxScore: 1,
        feedback: "The updated proof compiles cleanly and closes every goal with no remaining placeholders.",
        evaluationInput: "lake env lean proof.lean",
        error: null,
        evaluatedActionIds: [FIXTURE_IDS.actionId],
        evaluatedResourceIds: ["resource-proof"],
      },
    ],
  };
}

export function createDashboardSeed(): DashboardHarnessSeedPayload {
  const runState = serializedRunState();
  const summary = {
    cohort_id: FIXTURE_IDS.cohortId,
    name: "minif2f-react-worker-gpt5v3",
    description: "Deterministic fixture cohort for browser tests.",
    created_by: "playwright",
    created_at: "2026-03-18T11:59:00.000Z",
    status: "active" as const,
    total_runs: 1,
    status_counts: {
      pending: 0,
      executing: 1,
      evaluating: 0,
      completed: 0,
      failed: 0,
    },
    average_score: null,
    best_score: null,
    worst_score: null,
    average_duration_ms: null,
    failure_rate: 0,
    metadata_summary: {
      code_commit_sha: "abc1234",
      repo_dirty: false,
      prompt_version: "v1",
      worker_version: "react-worker-v3",
      model_provider: "openai",
      model_name: "gpt-5",
      sandbox_config: {
        template: "lean4",
        timeout_minutes: 30,
      },
      dispatch_config: {
        worker_model: "gpt-5",
        max_questions: 8,
      },
    },
    stats_updated_at: "2026-03-18T12:00:20.000Z",
    extras: {
      benchmark_counts: {
        minif2f: 1,
      },
      latest_run_at: "2026-03-18T12:00:00.000Z",
    },
  };

  const detail = {
    summary,
    runs: [
      {
        run_id: FIXTURE_IDS.runId,
        definition_id: FIXTURE_IDS.experimentId,
        cohort_id: FIXTURE_IDS.cohortId,
        cohort_name: summary.name,
        status: "executing",
        created_at: "2026-03-18T11:59:30.000Z",
        started_at: "2026-03-18T12:00:00.000Z",
        completed_at: null,
        running_time_ms: 24_000,
        final_score: null,
        error_message: null,
      },
    ],
  };

  return {
    cohorts: [summary],
    cohortDetails: {
      [FIXTURE_IDS.cohortId]: detail,
    },
    runs: [runState],
  };
}
