/* eslint-disable @typescript-eslint/no-empty-object-type */
import { z } from "zod";

type JsonValue_Input =
  | (JsonScalar | Array<JsonValue_Input> | {})
  | Array<JsonScalar | Array<JsonValue_Input> | {}>;
type JsonScalar =
  | (string | number | number | boolean | null)
  | Array<string | number | number | boolean | null>;
type JsonValue_Output =
  | (JsonScalar | Array<JsonValue_Output> | {})
  | Array<JsonScalar | Array<JsonValue_Output> | {}>;

const RunTaskDto = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  status: z.string(),
  parentId: z.union([z.string(), z.null()]).optional(),
  childIds: z.array(z.string()).optional(),
  dependsOnIds: z.array(z.string()).optional(),
  isLeaf: z.boolean(),
  level: z.number().int(),
  assignedWorkerId: z.union([z.string(), z.null()]).optional(),
  assignedWorkerSlug: z.union([z.string(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
});
const RunResourceDto = z.object({
  id: z.string(),
  taskId: z.string(),
  taskExecutionId: z.string(),
  name: z.string(),
  mimeType: z.string(),
  filePath: z.string(),
  sizeBytes: z.number().int(),
  createdAt: z.string().datetime({ offset: true }),
});
const RunExecutionAttemptDto = z.object({
  id: z.string(),
  taskId: z.string(),
  attemptNumber: z.number().int(),
  status: z.string(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  finalAssistantMessage: z.union([z.string(), z.null()]).optional(),
  errorMessage: z.union([z.string(), z.null()]).optional(),
  score: z.union([z.number(), z.null()]).optional(),
  agentId: z.union([z.string(), z.null()]).optional(),
  agentName: z.union([z.string(), z.null()]).optional(),
  evaluationDetails: z
    .union([z.object({}).partial().passthrough(), z.null()])
    .optional(),
  outputResourceIds: z.array(z.string()).optional(),
});
const RunEvaluationCriterionDto = z.object({
  id: z.string(),
  stageNum: z.number().int(),
  stageName: z.string(),
  criterionNum: z.number().int(),
  criterionSlug: z.string(),
  criterionType: z.string(),
  criterionDescription: z.string(),
  criterionName: z.string(),
  status: z.enum(["passed", "failed", "errored", "skipped"]),
  passed: z.boolean(),
  weight: z.number(),
  contribution: z.number(),
  evaluationInput: z.union([z.string(), z.null()]).optional(),
  score: z.number(),
  maxScore: z.number(),
  feedback: z.union([z.string(), z.null()]).optional(),
  modelReasoning: z.union([z.string(), z.null()]).optional(),
  skippedReason: z.union([z.string(), z.null()]).optional(),
  evaluatedActionIds: z.array(z.string()).optional(),
  evaluatedResourceIds: z.array(z.string()).optional(),
  observation: z
    .union([z.object({}).partial().passthrough(), z.null()])
    .optional(),
  error: z.union([z.object({}).partial().passthrough(), z.null()]).optional(),
});
const RunTaskEvaluationDto = z.object({
  id: z.string(),
  runId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
  evaluatorName: z.string(),
  aggregationRule: z.string(),
  totalScore: z.number(),
  maxScore: z.number(),
  normalizedScore: z.number(),
  stagesEvaluated: z.number().int(),
  stagesPassed: z.number().int(),
  failedGate: z.union([z.string(), z.null()]).optional(),
  createdAt: z.string().datetime({ offset: true }),
  criterionResults: z.array(RunEvaluationCriterionDto).optional(),
});
const RunSandboxCommandDto = z.object({
  command: z.string(),
  stdout: z.union([z.string(), z.null()]).optional(),
  stderr: z.union([z.string(), z.null()]).optional(),
  exitCode: z.union([z.number(), z.null()]).optional(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  timestamp: z.string().datetime({ offset: true }),
});
const RunSandboxDto = z.object({
  sandboxId: z.string(),
  taskId: z.string(),
  template: z.union([z.string(), z.null()]).optional(),
  timeoutMinutes: z.number().int(),
  status: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  closedAt: z.union([z.string(), z.null()]).optional(),
  closeReason: z.union([z.string(), z.null()]).optional(),
  commands: z.array(RunSandboxCommandDto).optional(),
});
const SystemPromptPart = z
  .object({
    part_kind: z.literal("system_prompt").default("system_prompt"),
    content: z.string(),
  })
  .passthrough();
const UserMessagePart = z
  .object({
    part_kind: z.literal("user_message").default("user_message"),
    content: z.string(),
  })
  .passthrough();
const AssistantTextPart = z
  .object({
    part_kind: z.literal("assistant_text").default("assistant_text"),
    content: z.string(),
  })
  .passthrough();
const ToolCallPart = z
  .object({
    part_kind: z.literal("tool_call").default("tool_call"),
    tool_name: z.string(),
    tool_call_id: z.string(),
    args: z.object({}).partial().passthrough(),
  })
  .passthrough();
const ToolResultPart = z
  .object({
    part_kind: z.literal("tool_result").default("tool_result"),
    tool_call_id: z.string(),
    tool_name: z.string(),
    content: z.string(),
    is_error: z.boolean().optional().default(false),
  })
  .passthrough();
const ThinkingPart = z
  .object({
    part_kind: z.literal("thinking").default("thinking"),
    content: z.string(),
  })
  .passthrough();
const JsonScalar = z.union([
  z.string(),
  z.number(),
  z.number(),
  z.boolean(),
  z.null(),
]);
const JsonValue_Output: z.ZodType<JsonValue_Output> = z.lazy(() => z.union([
  JsonScalar,
  z.array(JsonValue_Output),
  z.record(z.string(), JsonValue_Output),
]));
const JsonObject_Output = z.record(z.string(), JsonValue_Output);
const TokenLogprob = z
  .object({
    token: z.string(),
    logprob: z.number(),
    top_logprobs: z.array(JsonObject_Output).optional(),
  })
  .passthrough();
const ContextPartChunkLog = z
  .object({
    part: z.discriminatedUnion("part_kind", [
      SystemPromptPart,
      UserMessagePart,
      AssistantTextPart,
      ToolCallPart,
      ToolResultPart,
      ThinkingPart,
    ]),
    token_ids: z.union([z.array(z.number().int()), z.null()]).optional(),
    logprobs: z.union([z.array(TokenLogprob), z.null()]).optional(),
    sequence: z.number().int(),
    worker_binding_key: z.string(),
    turn_id: z.union([z.string(), z.null()]).optional(),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    policy_version: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const RunContextEventDto = z.object({
  id: z.string().uuid(),
  runId: z.string().uuid(),
  taskExecutionId: z.string().uuid(),
  taskNodeId: z.string().uuid(),
  workerBindingKey: z.string(),
  sequence: z.number().int(),
  eventType: z.enum([
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
  ]),
  payload: ContextPartChunkLog,
  createdAt: z.string().datetime({ offset: true }),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
});
const RunCommunicationMessageDto = z.object({
  id: z.string(),
  threadId: z.string(),
  threadTopic: z.string(),
  runId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
  taskExecutionId: z.union([z.string(), z.null()]).optional(),
  fromAgentId: z.string(),
  toAgentId: z.string(),
  content: z.string(),
  sequenceNum: z.number().int(),
  createdAt: z.string().datetime({ offset: true }),
});
const RunCommunicationThreadDto = z.object({
  id: z.string(),
  runId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
  topic: z.string(),
  summary: z.union([z.string(), z.null()]).optional(),
  agentAId: z.string(),
  agentBId: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  updatedAt: z.string().datetime({ offset: true }),
  messages: z.array(RunCommunicationMessageDto).optional(),
});
const RunSnapshotDto = z.object({
  id: z.string(),
  experimentId: z.string(),
  name: z.string(),
  status: z.string(),
  tasks: z.record(z.string(), RunTaskDto).optional(),
  rootTaskId: z.string().optional().default(""),
  resourcesByTask: z.record(z.string(), z.array(RunResourceDto)).optional(),
  executionsByTask: z.record(z.string(), z.array(RunExecutionAttemptDto)).optional(),
  evaluationsByTask: z.record(z.string(), RunTaskEvaluationDto).optional(),
  sandboxesByTask: z.record(z.string(), RunSandboxDto).optional(),
  contextEventsByTask: z.record(z.string(), z.array(RunContextEventDto)).optional(),
  threads: z.array(RunCommunicationThreadDto).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  durationSeconds: z.union([z.number(), z.null()]).optional(),
  totalTasks: z.number().int().optional().default(0),
  totalLeafTasks: z.number().int().optional().default(0),
  completedTasks: z.number().int().optional().default(0),
  failedTasks: z.number().int().optional().default(0),
  runningTasks: z.number().int().optional().default(0),
  cancelledTasks: z.number().int().optional().default(0),
  finalScore: z.union([z.number(), z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
});
const ValidationError = z
  .object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
    input: z.unknown().optional(),
    ctx: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const HTTPValidationError = z
  .object({ detail: z.array(ValidationError) })
  .partial()
  .passthrough();
const NodeAddedMutation = z
  .object({
    mutation_type: z.string().optional().default("node.added"),
    task_slug: z.string(),
    instance_key: z.string(),
    description: z.string(),
    status: z.string(),
    assigned_worker_slug: z.union([z.string(), z.null()]),
  })
  .passthrough();
const NodeRemovedMutation = z
  .object({
    mutation_type: z.string().optional().default("node.removed"),
    task_slug: z.string(),
    instance_key: z.string(),
    description: z.string(),
    status: z.string(),
    assigned_worker_slug: z.union([z.string(), z.null()]),
  })
  .passthrough();
const NodeStatusChangedMutation = z
  .object({
    mutation_type: z.string().optional().default("node.status_changed"),
    status: z.string(),
  })
  .passthrough();
const NodeFieldChangedMutation = z
  .object({
    mutation_type: z.string().optional().default("node.field_changed"),
    field: z.enum(["description", "assigned_worker_slug"]),
    value: z.union([z.string(), z.null()]),
  })
  .passthrough();
const EdgeAddedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.added"),
    source_node_id: z.string().uuid(),
    target_node_id: z.string().uuid(),
    status: z.string(),
  })
  .passthrough();
const EdgeRemovedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.removed"),
    source_node_id: z.string().uuid(),
    target_node_id: z.string().uuid(),
    status: z.string(),
  })
  .passthrough();
const EdgeStatusChangedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.status_changed"),
    status: z.string(),
  })
  .passthrough();
const AnnotationSetMutation = z
  .object({
    mutation_type: z.string().optional().default("annotation.set"),
    namespace: z.string(),
    payload: JsonObject_Output,
  })
  .passthrough();
const AnnotationDeletedMutation = z
  .object({
    mutation_type: z.string().optional().default("annotation.deleted"),
    namespace: z.string(),
    payload: JsonObject_Output,
  })
  .passthrough();
const GraphMutationRecordDto = z
  .object({
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    sequence: z.number().int(),
    mutation_type: z.enum([
      "node.added",
      "node.removed",
      "node.status_changed",
      "node.field_changed",
      "edge.added",
      "edge.removed",
      "edge.status_changed",
      "annotation.set",
      "annotation.deleted",
    ]),
    target_type: z.enum(["node", "edge"]),
    target_id: z.string().uuid(),
    actor: z.string(),
    old_value: z.union([
      z.discriminatedUnion("mutation_type", [
        NodeAddedMutation,
        NodeRemovedMutation,
        NodeStatusChangedMutation,
        NodeFieldChangedMutation,
        EdgeAddedMutation,
        EdgeRemovedMutation,
        EdgeStatusChangedMutation,
        AnnotationSetMutation,
        AnnotationDeletedMutation,
      ]),
      z.null(),
    ]),
    new_value: z.discriminatedUnion("mutation_type", [
      NodeAddedMutation,
      NodeRemovedMutation,
      NodeStatusChangedMutation,
      NodeFieldChangedMutation,
      EdgeAddedMutation,
      EdgeRemovedMutation,
      EdgeStatusChangedMutation,
      AnnotationSetMutation,
      AnnotationDeletedMutation,
    ]),
    reason: z.union([z.string(), z.null()]),
    created_at: z.string().datetime({ offset: true }),
  })
  .passthrough();
const definition_id = z.union([z.string(), z.null()]).optional();
const TrainingCurvePointDto = z.object({
  runId: z.string(),
  step: z.number().int(),
  meanScore: z.number(),
  benchmarkType: z.union([z.string(), z.null()]).optional(),
  createdAt: z.union([z.string(), z.null()]).optional(),
});
const TrainingSessionDto = z.object({
  id: z.string(),
  experimentDefinitionId: z.string(),
  modelName: z.string(),
  status: z.string(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  outputDir: z.union([z.string(), z.null()]).optional(),
  totalSteps: z.union([z.number(), z.null()]).optional(),
  finalLoss: z.union([z.number(), z.null()]).optional(),
});
const TrainingMetricDto = z.object({
  step: z.number().int(),
  epoch: z.union([z.number(), z.null()]).optional(),
  loss: z.union([z.number(), z.null()]).optional(),
  gradNorm: z.union([z.number(), z.null()]).optional(),
  learningRate: z.union([z.number(), z.null()]).optional(),
  rewardMean: z.union([z.number(), z.null()]).optional(),
  rewardStd: z.union([z.number(), z.null()]).optional(),
  entropy: z.union([z.number(), z.null()]).optional(),
  completionMeanLength: z.union([z.number(), z.null()]).optional(),
  stepTimeS: z.union([z.number(), z.null()]).optional(),
});
const CohortStatusCountsDto = z
  .object({
    pending: z.number().int().default(0),
    executing: z.number().int().default(0),
    evaluating: z.number().int().default(0),
    completed: z.number().int().default(0),
    failed: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const CohortSummaryDto = z
  .object({
    cohort_id: z.string().uuid(),
    name: z.string(),
    description: z.union([z.string(), z.null()]).optional(),
    created_by: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    status: z.string(),
    total_runs: z.number().int().optional().default(0),
    status_counts: CohortStatusCountsDto.optional(),
    average_score: z.union([z.number(), z.null()]).optional(),
    best_score: z.union([z.number(), z.null()]).optional(),
    worst_score: z.union([z.number(), z.null()]).optional(),
    average_duration_ms: z.union([z.number(), z.null()]).optional(),
    failure_rate: z.number().optional().default(0),
    stats_updated_at: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const CohortExperimentRowDto = z
  .object({
    experiment_id: z.string().uuid(),
    name: z.string(),
    benchmark_type: z.string(),
    sample_count: z.number().int(),
    total_runs: z.number().int().optional().default(0),
    status_counts: CohortStatusCountsDto.optional(),
    status: z.string(),
    created_at: z.string().datetime({ offset: true }),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    final_score: z.union([z.number(), z.null()]).optional(),
    total_cost_usd: z.union([z.number(), z.null()]).optional(),
    error_message: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const CohortDetailDto = z
  .object({
    summary: CohortSummaryDto,
    experiments: z.array(CohortExperimentRowDto).optional(),
  })
  .passthrough();
const ExperimentCohortStatus = z.enum(["active", "archived"]);
const UpdateCohortRequest = z
  .object({ status: ExperimentCohortStatus })
  .passthrough();
const ExperimentSummaryDto = z
  .object({
    experiment_id: z.string().uuid(),
    cohort_id: z.union([z.string(), z.null()]).optional(),
    name: z.string(),
    benchmark_type: z.string(),
    sample_count: z.number().int(),
    status: z.string(),
    default_worker_team: z.object({}).partial().passthrough().optional(),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    run_count: z.number().int().optional().default(0),
  })
  .passthrough();
const ExperimentRunRowDto = z
  .object({
    run_id: z.string().uuid(),
    workflow_definition_id: z.string().uuid(),
    benchmark_type: z.string(),
    instance_key: z.string(),
    status: z.string(),
    created_at: z.string().datetime({ offset: true }),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    evaluator_slug: z.union([z.string(), z.null()]).optional(),
    model_target: z.union([z.string(), z.null()]).optional(),
    worker_team: z.object({}).partial().passthrough().optional(),
    seed: z.union([z.number(), z.null()]).optional(),
    running_time_ms: z.union([z.number(), z.null()]).optional(),
    final_score: z.union([z.number(), z.null()]).optional(),
    total_tasks: z.union([z.number(), z.null()]).optional(),
    total_cost_usd: z.union([z.number(), z.null()]).optional(),
    error_message: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const ExperimentStatusCountsDto = z
  .object({
    pending: z.number().int().default(0),
    executing: z.number().int().default(0),
    evaluating: z.number().int().default(0),
    completed: z.number().int().default(0),
    failed: z.number().int().default(0),
    cancelled: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const ExperimentAnalyticsDto = z
  .object({
    total_runs: z.number().int().default(0),
    status_counts: ExperimentStatusCountsDto,
    average_score: z.union([z.number(), z.null()]),
    average_duration_ms: z.union([z.number(), z.null()]),
    average_tasks: z.union([z.number(), z.null()]),
    total_cost_usd: z.union([z.number(), z.null()]),
    latest_activity_at: z.union([z.string(), z.null()]),
    error_count: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const ExperimentDetailDto = z
  .object({
    experiment: ExperimentSummaryDto,
    runs: z.array(ExperimentRunRowDto).optional(),
    analytics: ExperimentAnalyticsDto.optional(),
    sample_selection: z.object({}).partial().passthrough().optional(),
    design: z.object({}).partial().passthrough().optional(),
    metadata: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const JsonValue_Input: z.ZodType<JsonValue_Input> = z.lazy(() => z.union([
  JsonScalar,
  z.array(JsonValue_Input),
  z.record(z.string(), JsonValue_Input),
]));
const JsonObject_Input = z.record(z.string(), JsonValue_Input);
const ExperimentDefineRequest = z
  .object({
    benchmark_slug: z.string(),
    name: z.union([z.string(), z.null()]).optional(),
    cohort_id: z.union([z.string(), z.null()]).optional(),
    limit: z.union([z.number(), z.null()]).optional(),
    sample_ids: z.union([z.array(z.string()), z.null()]).optional(),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    default_worker_team: JsonObject_Input.optional(),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    design: JsonObject_Input.optional(),
    seed: z.union([z.number(), z.null()]).optional(),
    metadata: JsonObject_Input.optional(),
  })
  .passthrough();
const ExperimentDefineResult = z
  .object({
    experiment_id: z.string().uuid(),
    cohort_id: z.union([z.string(), z.null()]),
    benchmark_type: z.string(),
    sample_count: z.number().int(),
    selected_samples: z.array(z.string()),
  })
  .passthrough();
const ExperimentRunRequest = z
  .object({
    experiment_id: z.string().uuid(),
    timeout_seconds: z.union([z.number(), z.null()]).optional(),
    wait: z.boolean().optional().default(true),
  })
  .passthrough();
const run_experiment_experiments__experiment_id__run_post_Body = z.union([
  ExperimentRunRequest,
  z.null(),
]);
const ExperimentRunResult = z
  .object({
    experiment_id: z.string().uuid(),
    run_ids: z.array(z.string().uuid()),
    workflow_definition_ids: z.array(z.string().uuid()).optional(),
  })
  .passthrough();
const SubmitRequest = z
  .object({
    definition_id: z.string().uuid(),
    num_episodes: z.number().int().gte(1),
    policy_version: z.union([z.number(), z.null()]).optional(),
    model_target_override: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const BatchStatus = z.enum([
  "pending",
  "running",
  "complete",
  "failed",
  "cancelled",
]);
const SubmitResponse = z
  .object({
    batch_id: z.string().uuid(),
    run_ids: z.array(z.string().uuid()),
    status: BatchStatus.optional(),
  })
  .passthrough();
const Trajectory = z
  .object({
    run_id: z.string().uuid(),
    agent_id: z.string(),
    prompt_ids: z.array(z.number().int()),
    completion_ids: z.array(z.number().int()),
    logprobs: z.array(z.number()),
    env_mask: z.array(z.number().int()),
    reward: z.number(),
    num_turns: z.number().int(),
  })
  .passthrough();
const EpisodeFailure = z
  .object({ run_id: z.string().uuid(), error: z.string() })
  .passthrough();
const PollResponse = z
  .object({
    batch_id: z.string().uuid(),
    status: BatchStatus,
    completed: z.number().int().optional().default(0),
    total: z.number().int().optional().default(0),
    trajectories: z.array(Trajectory).optional(),
    failures: z.array(EpisodeFailure).optional(),
  })
  .passthrough();
const WeightSyncRequest = z
  .object({ checkpoint_path: z.string(), model_name: z.string() })
  .passthrough();
const WeightSyncResponse = z
  .object({ success: z.boolean(), vllm_model_loaded: z.string() })
  .passthrough();

export const schemas = {
  RunTaskDto,
  RunResourceDto,
  RunExecutionAttemptDto,
  RunEvaluationCriterionDto,
  RunTaskEvaluationDto,
  RunSandboxCommandDto,
  RunSandboxDto,
  SystemPromptPart,
  UserMessagePart,
  AssistantTextPart,
  ToolCallPart,
  ToolResultPart,
  ThinkingPart,
  JsonScalar,
  JsonValue_Output,
  JsonObject_Output,
  TokenLogprob,
  ContextPartChunkLog,
  RunContextEventDto,
  RunCommunicationMessageDto,
  RunCommunicationThreadDto,
  RunSnapshotDto,
  ValidationError,
  HTTPValidationError,
  NodeAddedMutation,
  NodeRemovedMutation,
  NodeStatusChangedMutation,
  NodeFieldChangedMutation,
  EdgeAddedMutation,
  EdgeRemovedMutation,
  EdgeStatusChangedMutation,
  AnnotationSetMutation,
  AnnotationDeletedMutation,
  GraphMutationRecordDto,
  definition_id,
  TrainingCurvePointDto,
  TrainingSessionDto,
  TrainingMetricDto,
  CohortStatusCountsDto,
  CohortSummaryDto,
  CohortExperimentRowDto,
  CohortDetailDto,
  ExperimentCohortStatus,
  UpdateCohortRequest,
  ExperimentSummaryDto,
  ExperimentRunRowDto,
  ExperimentStatusCountsDto,
  ExperimentAnalyticsDto,
  ExperimentDetailDto,
  JsonValue_Input,
  JsonObject_Input,
  ExperimentDefineRequest,
  ExperimentDefineResult,
  ExperimentRunRequest,
  run_experiment_experiments__experiment_id__run_post_Body,
  ExperimentRunResult,
  SubmitRequest,
  BatchStatus,
  SubmitResponse,
  Trajectory,
  EpisodeFailure,
  PollResponse,
  WeightSyncRequest,
  WeightSyncResponse,
};
