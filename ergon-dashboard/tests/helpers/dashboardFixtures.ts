import type { DashboardHarnessSeedPayload } from "../../src/lib/testing/dashboardHarness";
import concurrentMasFixture from "../fixtures/mas-runs/concurrent-mas-run.json";
import type {
  CommunicationThreadState,
  ContextEventState,
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
  toolCallEventId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  toolResultEventId: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  deltaToolCallEventId: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
} as const;

export const CONCURRENT_MAS_FIXTURE_IDS = {
  cohortId: "12121212-1212-4121-8121-121212121212",
  experimentId: "33333333-3333-4333-8333-333333333333",
  runId: "99999999-9999-4999-8999-999999999999",
  searchTaskId: "10000000-0000-4000-8000-000000000002",
  checkTaskId: "10000000-0000-4000-8000-000000000003",
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
  const solveContextEvents: ContextEventState[] = [
    {
      id: FIXTURE_IDS.toolCallEventId,
      taskExecutionId: "execution-solve-1",
      taskNodeId: FIXTURE_IDS.solveTaskId,
      workerBindingKey: "react-worker",
      sequence: 0,
      eventType: "tool_call",
      payload: {
        event_type: "tool_call",
        tool_call_id: "call-lean-check",
        tool_name: "lean_check",
        args: { file: "proof.lean" },
        turn_id: "turn-1",
        turn_token_ids: [101, 102, 103],
        turn_logprobs: null,
      },
      createdAt: "2026-03-18T12:00:18.000Z",
      startedAt: "2026-03-18T12:00:18.000Z",
      completedAt: "2026-03-18T12:00:18.100Z",
    },
    {
      id: FIXTURE_IDS.toolResultEventId,
      taskExecutionId: "execution-solve-1",
      taskNodeId: FIXTURE_IDS.solveTaskId,
      workerBindingKey: "react-worker",
      sequence: 1,
      eventType: "tool_result",
      payload: {
        event_type: "tool_result",
        tool_call_id: "call-lean-check",
        tool_name: "lean_check",
        result: "checking proof...",
        is_error: false,
      },
      createdAt: "2026-03-18T12:00:19.000Z",
      startedAt: null,
      completedAt: null,
    },
  ];

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
    contextEventsByTask: {
      [FIXTURE_IDS.solveTaskId]: solveContextEvents,
    },
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
          finalAssistantMessage: "Relevant divisibility lemmas identified.",
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
          finalAssistantMessage: null,
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
    cancelledTasks: 0,
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

export function createDeltaContextEvent(): ContextEventState {
  return {
    id: FIXTURE_IDS.deltaToolCallEventId,
    taskExecutionId: "execution-solve-1",
    taskNodeId: FIXTURE_IDS.solveTaskId,
    workerBindingKey: "react-worker",
    sequence: 2,
    eventType: "tool_call",
    payload: {
      event_type: "tool_call",
      tool_call_id: "call-lake-build",
      tool_name: "lake_build",
      args: { target: "Proof" },
      turn_id: "turn-2",
      turn_token_ids: [201, 202],
      turn_logprobs: null,
    },
    createdAt: "2026-03-18T12:00:25.000Z",
    startedAt: "2026-03-18T12:00:25.000Z",
    completedAt: "2026-03-18T12:00:26.000Z",
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

export function createEmptyCriteriaEvaluation(): TaskEvaluationState {
  return {
    id: FIXTURE_IDS.evaluationId,
    runId: FIXTURE_IDS.runId,
    taskId: FIXTURE_IDS.solveTaskId,
    totalScore: 0,
    maxScore: 0,
    normalizedScore: 0,
    stagesEvaluated: 0,
    stagesPassed: 0,
    failedGate: null,
    createdAt: "2026-03-18T12:00:31.000Z",
    criterionResults: [],
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
    total_runs: 3,
    status_counts: {
      pending: 0,
      executing: 0,
      evaluating: 0,
      completed: 3,
      failed: 0,
    },
    average_score: 1,
    best_score: 1,
    worst_score: 1,
    average_duration_ms: 24_000,
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
    experiments: [
      {
        experiment_id: FIXTURE_IDS.experimentId,
        name: "minif2f smoke n=3",
        benchmark_type: "minif2f",
        sample_count: 3,
        total_runs: 3,
        status_counts: {
          pending: 0,
          executing: 0,
          evaluating: 0,
          completed: 3,
          failed: 0,
        },
        status: "completed",
        created_at: "2026-03-18T11:59:30.000Z",
        default_model_target: "openai:gpt-5",
        default_evaluator_slug: "lean-evaluator",
        final_score: 1,
        total_cost_usd: 0.42,
        error_message: null,
      },
    ],
  };

  const experimentDetail = {
    experiment: {
      experiment_id: FIXTURE_IDS.experimentId,
      cohort_id: FIXTURE_IDS.cohortId,
      name: "minif2f smoke n=3",
      benchmark_type: "minif2f",
      sample_count: 3,
      status: "completed",
      default_worker_team: { primary: "minif2f-react" },
      default_evaluator_slug: "lean-evaluator",
      default_model_target: "openai:gpt-5",
      created_at: "2026-03-18T11:59:30.000Z",
      started_at: "2026-03-18T12:00:00.000Z",
      completed_at: "2026-03-18T12:02:26.000Z",
      run_count: 3,
    },
    runs: [
      {
        run_id: FIXTURE_IDS.runId,
        workflow_definition_id: FIXTURE_IDS.experimentId,
        benchmark_type: "minif2f",
        instance_key: "algebra_sample",
        status: "completed",
        created_at: "2026-03-18T11:59:30.000Z",
        started_at: "2026-03-18T12:00:00.000Z",
        completed_at: "2026-03-18T12:00:24.000Z",
        evaluator_slug: "lean-evaluator",
        model_target: "openai:gpt-5",
        worker_team: { primary: "minif2f-react" },
        seed: null,
        running_time_ms: 24_000,
        final_score: 1,
        total_tasks: 10,
        total_cost_usd: 0.12,
        error_message: null,
      },
    ],
    analytics: {
      total_runs: 3,
      status_counts: {
        pending: 0,
        executing: 0,
        evaluating: 0,
        completed: 3,
        failed: 0,
        cancelled: 0,
      },
      average_score: 1,
      average_duration_ms: 24_000,
      average_tasks: 10,
      total_cost_usd: 0.42,
      latest_activity_at: "2026-03-18T12:02:26.000Z",
      error_count: 0,
    },
    sample_selection: { instance_keys: ["algebra_sample", "number_theory_sample", "geometry_sample"] },
    design: {},
    metadata: {},
  };

  const concurrent = createConcurrentMasSeedOnly();
  return {
    cohorts: [summary, ...(concurrent.cohorts ?? [])],
    cohortDetails: {
      [FIXTURE_IDS.cohortId]: detail,
      ...(concurrent.cohortDetails ?? {}),
    },
    experimentDetails: {
      [FIXTURE_IDS.experimentId]: experimentDetail,
      ...(concurrent.experimentDetails ?? {}),
    },
    runs: [runState, ...(concurrent.runs ?? [])],
    mutations: concurrent.mutations,
  };
}

function createConcurrentMasSeedOnly(): DashboardHarnessSeedPayload {
  const summary = {
    cohort_id: CONCURRENT_MAS_FIXTURE_IDS.cohortId,
    name: "concurrent-mas-visual-debugger",
    description: "Deterministic concurrent MAS fixture for visual debugger tests.",
    created_by: "playwright",
    created_at: "2026-04-26T11:59:00.000Z",
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
      code_commit_sha: "visual-debugger",
      repo_dirty: false,
      prompt_version: "visual-debugger-fixture",
      worker_version: "fixture",
      model_provider: "fixture",
      model_name: "fixture",
      sandbox_config: {
        template: "research",
        timeout_minutes: 30,
      },
      dispatch_config: {
        scenario: "concurrent-mas",
      },
    },
    stats_updated_at: "2026-04-26T12:00:30.000Z",
    extras: {
      benchmark_counts: {
        visual_debugger: 1,
      },
      latest_run_at: "2026-04-26T12:00:00.000Z",
    },
  };

  const detail = {
    summary,
    experiments: [
      {
        experiment_id: CONCURRENT_MAS_FIXTURE_IDS.experimentId,
        name: "visual debugger n=1",
        benchmark_type: "visual_debugger",
        sample_count: 1,
        total_runs: 1,
        status_counts: {
          pending: 0,
          executing: 1,
          evaluating: 0,
          completed: 0,
          failed: 0,
        },
        status: "executing",
        created_at: "2026-04-26T11:59:30.000Z",
        default_model_target: "fixture",
        default_evaluator_slug: null,
        final_score: null,
        total_cost_usd: null,
        error_message: null,
      },
    ],
  };

  return {
    cohorts: [summary],
    cohortDetails: {
      [CONCURRENT_MAS_FIXTURE_IDS.cohortId]: detail,
    },
    experimentDetails: {},
    runs: [concurrentMasFixture.runState as SerializedWorkflowRunState],
    mutations: {
      [CONCURRENT_MAS_FIXTURE_IDS.runId]: concurrentMasFixture.mutations,
    },
  } as DashboardHarnessSeedPayload;
}

export function createConcurrentMasDashboardSeed(): DashboardHarnessSeedPayload {
  return createDashboardSeed();
}
