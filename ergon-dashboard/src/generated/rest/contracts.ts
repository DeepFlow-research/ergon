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

const CohortStatusCountsDto = z
  .object({
    completed: z.number().int().default(0),
    evaluating: z.number().int().default(0),
    executing: z.number().int().default(0),
    failed: z.number().int().default(0),
    pending: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const CohortSummaryDto = z
  .object({
    average_duration_ms: z.union([z.number(), z.null()]).optional(),
    average_score: z.union([z.number(), z.null()]).optional(),
    best_score: z.union([z.number(), z.null()]).optional(),
    cohort_id: z.string().uuid(),
    created_at: z.string().datetime({ offset: true }),
    created_by: z.union([z.string(), z.null()]).optional(),
    description: z.union([z.string(), z.null()]).optional(),
    failure_rate: z.number().optional().default(0),
    name: z.string(),
    stats_updated_at: z.union([z.string(), z.null()]).optional(),
    status: z.string(),
    status_counts: CohortStatusCountsDto.optional(),
    total_runs: z.number().int().optional().default(0),
    worst_score: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const ValidationError = z
  .object({
    ctx: z.object({}).partial().passthrough().optional(),
    input: z.unknown().optional(),
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
  })
  .passthrough();
const HTTPValidationError = z
  .object({ detail: z.array(ValidationError) })
  .partial()
  .passthrough();
const CohortExperimentRowDto = z
  .object({
    benchmark_type: z.string(),
    created_at: z.string().datetime({ offset: true }),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    error_message: z.union([z.string(), z.null()]).optional(),
    experiment_id: z.string().uuid(),
    final_score: z.union([z.number(), z.null()]).optional(),
    name: z.string(),
    sample_count: z.number().int(),
    status: z.string(),
    status_counts: CohortStatusCountsDto.optional(),
    total_cost_usd: z.union([z.number(), z.null()]).optional(),
    total_runs: z.number().int().optional().default(0),
  })
  .passthrough();
const CohortDetailDto = z
  .object({
    experiments: z.array(CohortExperimentRowDto).optional(),
    summary: CohortSummaryDto,
  })
  .passthrough();
const ExperimentCohortStatus = z.enum(["active", "archived"]);
const UpdateCohortRequest = z
  .object({ status: ExperimentCohortStatus })
  .passthrough();
const ExperimentSummaryDto = z
  .object({
    benchmark_type: z.string(),
    cohort_id: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    default_worker_team: z.object({}).partial().passthrough().optional(),
    experiment_id: z.string().uuid(),
    name: z.string(),
    run_count: z.number().int().optional().default(0),
    sample_count: z.number().int(),
    started_at: z.union([z.string(), z.null()]).optional(),
    status: z.string(),
  })
  .passthrough();
const JsonScalar = z.union([
  z.string(),
  z.number(),
  z.number(),
  z.boolean(),
  z.null(),
]);
const JsonValue_Input: z.ZodType<JsonValue_Input> = z.lazy(() => z.union([
  JsonScalar,
  z.array(JsonValue_Input),
  z.record(z.string(), JsonValue_Input),
]));
const JsonObject_Input = z.record(z.string(), JsonValue_Input);
const ExperimentDefineRequest = z
  .object({
    benchmark_slug: z.string(),
    cohort_id: z.union([z.string(), z.null()]).optional(),
    default_evaluator_slug: z.union([z.string(), z.null()]).optional(),
    default_model_target: z.union([z.string(), z.null()]).optional(),
    default_worker_team: JsonObject_Input.optional(),
    design: JsonObject_Input.optional(),
    limit: z.union([z.number(), z.null()]).optional(),
    metadata: JsonObject_Input.optional(),
    name: z.union([z.string(), z.null()]).optional(),
    sample_ids: z.union([z.array(z.string()), z.null()]).optional(),
    seed: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const ExperimentDefineResult = z
  .object({
    benchmark_type: z.string(),
    cohort_id: z.union([z.string(), z.null()]),
    experiment_id: z.string().uuid(),
    sample_count: z.number().int(),
    selected_samples: z.array(z.string()),
  })
  .passthrough();
const ExperimentStatusCountsDto = z
  .object({
    cancelled: z.number().int().default(0),
    completed: z.number().int().default(0),
    evaluating: z.number().int().default(0),
    executing: z.number().int().default(0),
    failed: z.number().int().default(0),
    pending: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const ExperimentAnalyticsDto = z
  .object({
    average_duration_ms: z.union([z.number(), z.null()]),
    average_score: z.union([z.number(), z.null()]),
    average_tasks: z.union([z.number(), z.null()]),
    error_count: z.number().int().default(0),
    latest_activity_at: z.union([z.string(), z.null()]),
    status_counts: ExperimentStatusCountsDto,
    total_cost_usd: z.union([z.number(), z.null()]),
    total_runs: z.number().int().default(0),
  })
  .partial()
  .passthrough();
const ExperimentRunRowDto = z
  .object({
    benchmark_type: z.string(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    error_message: z.union([z.string(), z.null()]).optional(),
    evaluator_slug: z.union([z.string(), z.null()]).optional(),
    final_score: z.union([z.number(), z.null()]).optional(),
    instance_key: z.string(),
    model_target: z.union([z.string(), z.null()]).optional(),
    run_id: z.string().uuid(),
    running_time_ms: z.union([z.number(), z.null()]).optional(),
    seed: z.union([z.number(), z.null()]).optional(),
    started_at: z.union([z.string(), z.null()]).optional(),
    status: z.string(),
    total_cost_usd: z.union([z.number(), z.null()]).optional(),
    total_tasks: z.union([z.number(), z.null()]).optional(),
    worker_team: z.object({}).partial().passthrough().optional(),
    workflow_definition_id: z.string().uuid(),
  })
  .passthrough();
const ExperimentDetailDto = z
  .object({
    analytics: ExperimentAnalyticsDto.optional(),
    design: z.object({}).partial().passthrough().optional(),
    experiment: ExperimentSummaryDto,
    metadata: z.object({}).partial().passthrough().optional(),
    runs: z.array(ExperimentRunRowDto).optional(),
    sample_selection: z.object({}).partial().passthrough().optional(),
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
    model_target_override: z.union([z.string(), z.null()]).optional(),
    num_episodes: z.number().int().gte(1),
    policy_version: z.union([z.number(), z.null()]).optional(),
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
const WeightSyncRequest = z
  .object({ checkpoint_path: z.string(), model_name: z.string() })
  .passthrough();
const WeightSyncResponse = z
  .object({ success: z.boolean(), vllm_model_loaded: z.string() })
  .passthrough();
const EpisodeFailure = z
  .object({ error: z.string(), run_id: z.string().uuid() })
  .passthrough();
const Trajectory = z
  .object({
    agent_id: z.string(),
    completion_ids: z.array(z.number().int()),
    env_mask: z.array(z.number().int()),
    logprobs: z.array(z.number()),
    num_turns: z.number().int(),
    prompt_ids: z.array(z.number().int()),
    reward: z.number(),
    run_id: z.string().uuid(),
  })
  .passthrough();
const PollResponse = z
  .object({
    batch_id: z.string().uuid(),
    completed: z.number().int().optional().default(0),
    failures: z.array(EpisodeFailure).optional(),
    status: BatchStatus,
    total: z.number().int().optional().default(0),
    trajectories: z.array(Trajectory).optional(),
  })
  .passthrough();
const definition_id = z.union([z.string(), z.null()]).optional();
const TrainingCurvePointDto = z.object({
  benchmarkType: z.union([z.string(), z.null()]).optional(),
  createdAt: z.union([z.string(), z.null()]).optional(),
  meanScore: z.number(),
  runId: z.string(),
  step: z.number().int(),
});
const TrainingSessionDto = z.object({
  completedAt: z.union([z.string(), z.null()]).optional(),
  experimentDefinitionId: z.string(),
  finalLoss: z.union([z.number(), z.null()]).optional(),
  id: z.string(),
  modelName: z.string(),
  outputDir: z.union([z.string(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
  totalSteps: z.union([z.number(), z.null()]).optional(),
});
const TrainingMetricDto = z.object({
  completionMeanLength: z.union([z.number(), z.null()]).optional(),
  entropy: z.union([z.number(), z.null()]).optional(),
  epoch: z.union([z.number(), z.null()]).optional(),
  gradNorm: z.union([z.number(), z.null()]).optional(),
  learningRate: z.union([z.number(), z.null()]).optional(),
  loss: z.union([z.number(), z.null()]).optional(),
  rewardMean: z.union([z.number(), z.null()]).optional(),
  rewardStd: z.union([z.number(), z.null()]).optional(),
  step: z.number().int(),
  stepTimeS: z.union([z.number(), z.null()]).optional(),
});
const RunContextEventDto = z.object({
  completedAt: z.union([z.string(), z.null()]).optional(),
  createdAt: z.string(),
  eventType: z.string(),
  id: z.string(),
  payload: z.object({}).partial().passthrough(),
  sequence: z.number().int(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  taskExecutionId: z.string(),
  taskNodeId: z.string(),
  workerBindingKey: z.string(),
});
const RunEvaluationCriterionDto = z.object({
  criterionDescription: z.string(),
  criterionNum: z.number().int(),
  criterionType: z.string(),
  error: z.union([z.object({}).partial().passthrough(), z.null()]).optional(),
  evaluatedActionIds: z.array(z.string()).optional(),
  evaluatedResourceIds: z.array(z.string()).optional(),
  evaluationInput: z.union([z.string(), z.null()]).optional(),
  feedback: z.union([z.string(), z.null()]).optional(),
  id: z.string(),
  maxScore: z.number(),
  score: z.number(),
  stageName: z.string(),
  stageNum: z.number().int(),
});
const RunTaskEvaluationDto = z.object({
  createdAt: z.string().datetime({ offset: true }),
  criterionResults: z.array(RunEvaluationCriterionDto).optional(),
  failedGate: z.union([z.string(), z.null()]).optional(),
  id: z.string(),
  maxScore: z.number(),
  normalizedScore: z.number(),
  runId: z.string(),
  stagesEvaluated: z.number().int(),
  stagesPassed: z.number().int(),
  taskId: z.union([z.string(), z.null()]).optional(),
  totalScore: z.number(),
});
const RunExecutionAttemptDto = z.object({
  agentId: z.union([z.string(), z.null()]).optional(),
  agentName: z.union([z.string(), z.null()]).optional(),
  attemptNumber: z.number().int(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  errorMessage: z.union([z.string(), z.null()]).optional(),
  evaluationDetails: z
    .union([z.object({}).partial().passthrough(), z.null()])
    .optional(),
  finalAssistantMessage: z.union([z.string(), z.null()]).optional(),
  id: z.string(),
  outputResourceIds: z.array(z.string()).optional(),
  score: z.union([z.number(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
  taskId: z.string(),
});
const RunResourceDto = z.object({
  createdAt: z.string().datetime({ offset: true }),
  filePath: z.string(),
  id: z.string(),
  mimeType: z.string(),
  name: z.string(),
  sizeBytes: z.number().int(),
  taskExecutionId: z.string(),
  taskId: z.string(),
});
const RunSandboxCommandDto = z.object({
  command: z.string(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  exitCode: z.union([z.number(), z.null()]).optional(),
  stderr: z.union([z.string(), z.null()]).optional(),
  stdout: z.union([z.string(), z.null()]).optional(),
  timestamp: z.string().datetime({ offset: true }),
});
const RunSandboxDto = z.object({
  closeReason: z.union([z.string(), z.null()]).optional(),
  closedAt: z.union([z.string(), z.null()]).optional(),
  commands: z.array(RunSandboxCommandDto).optional(),
  createdAt: z.string().datetime({ offset: true }),
  sandboxId: z.string(),
  status: z.string(),
  taskId: z.string(),
  template: z.union([z.string(), z.null()]).optional(),
  timeoutMinutes: z.number().int(),
});
const RunTaskDto = z.object({
  assignedWorkerId: z.union([z.string(), z.null()]).optional(),
  assignedWorkerName: z.union([z.string(), z.null()]).optional(),
  childIds: z.array(z.string()).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  dependsOnIds: z.array(z.string()).optional(),
  description: z.string(),
  id: z.string(),
  isLeaf: z.boolean(),
  level: z.number().int(),
  name: z.string(),
  parentId: z.union([z.string(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
});
const RunCommunicationMessageDto = z.object({
  content: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  fromAgentId: z.string(),
  id: z.string(),
  runId: z.string(),
  sequenceNum: z.number().int(),
  taskExecutionId: z.union([z.string(), z.null()]).optional(),
  taskId: z.union([z.string(), z.null()]).optional(),
  threadId: z.string(),
  threadTopic: z.string(),
  toAgentId: z.string(),
});
const RunCommunicationThreadDto = z.object({
  agentAId: z.string(),
  agentBId: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  id: z.string(),
  messages: z.array(RunCommunicationMessageDto).optional(),
  runId: z.string(),
  summary: z.union([z.string(), z.null()]).optional(),
  taskId: z.union([z.string(), z.null()]).optional(),
  topic: z.string(),
  updatedAt: z.string().datetime({ offset: true }),
});
const RunSnapshotDto = z.object({
  cancelledTasks: z.number().int().optional().default(0),
  completedAt: z.union([z.string(), z.null()]).optional(),
  completedTasks: z.number().int().optional().default(0),
  contextEventsByTask: z.record(z.string(), z.array(RunContextEventDto)).optional(),
  durationSeconds: z.union([z.number(), z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
  evaluationsByTask: z.record(z.string(), RunTaskEvaluationDto).optional(),
  executionsByTask: z.record(z.string(), z.array(RunExecutionAttemptDto)).optional(),
  experimentId: z.string(),
  failedTasks: z.number().int().optional().default(0),
  finalScore: z.union([z.number(), z.null()]).optional(),
  id: z.string(),
  name: z.string(),
  resourcesByTask: z.record(z.string(), z.array(RunResourceDto)).optional(),
  rootTaskId: z.string().optional().default(""),
  runningTasks: z.number().int().optional().default(0),
  sandboxesByTask: z.record(z.string(), RunSandboxDto).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
  tasks: z.record(z.string(), RunTaskDto).optional(),
  threads: z.array(RunCommunicationThreadDto).optional(),
  totalLeafTasks: z.number().int().optional().default(0),
  totalTasks: z.number().int().optional().default(0),
});
const NodeAddedMutation = z
  .object({
    assigned_worker_slug: z.union([z.string(), z.null()]),
    description: z.string(),
    instance_key: z.string(),
    mutation_type: z.string().optional().default("node.added"),
    status: z.string(),
    task_slug: z.string(),
  })
  .passthrough();
const NodeRemovedMutation = z
  .object({
    assigned_worker_slug: z.union([z.string(), z.null()]),
    description: z.string(),
    instance_key: z.string(),
    mutation_type: z.string().optional().default("node.removed"),
    status: z.string(),
    task_slug: z.string(),
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
    field: z.enum(["description", "assigned_worker_slug"]),
    mutation_type: z.string().optional().default("node.field_changed"),
    value: z.union([z.string(), z.null()]),
  })
  .passthrough();
const EdgeAddedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.added"),
    source_node_id: z.string(),
    status: z.string(),
    target_node_id: z.string(),
  })
  .passthrough();
const EdgeRemovedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.removed"),
    source_node_id: z.string(),
    status: z.string(),
    target_node_id: z.string(),
  })
  .passthrough();
const EdgeStatusChangedMutation = z
  .object({
    mutation_type: z.string().optional().default("edge.status_changed"),
    status: z.string(),
  })
  .passthrough();
const JsonValue_Output: z.ZodType<JsonValue_Output> = z.lazy(() => z.union([
  JsonScalar,
  z.array(JsonValue_Output),
  z.record(z.string(), JsonValue_Output),
]));
const JsonObject_Output = z.record(z.string(), JsonValue_Output);
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
const RunGraphMutationDto = z.object({
  actor: z.string(),
  created_at: z.string(),
  id: z.string(),
  mutation_type: z.string(),
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
  reason: z.union([z.string(), z.null()]),
  run_id: z.string(),
  sequence: z.number().int(),
  target_id: z.string(),
  target_type: z.string(),
});

export const schemas = {
  CohortStatusCountsDto,
  CohortSummaryDto,
  ValidationError,
  HTTPValidationError,
  CohortExperimentRowDto,
  CohortDetailDto,
  ExperimentCohortStatus,
  UpdateCohortRequest,
  ExperimentSummaryDto,
  JsonScalar,
  JsonValue_Input,
  JsonObject_Input,
  ExperimentDefineRequest,
  ExperimentDefineResult,
  ExperimentStatusCountsDto,
  ExperimentAnalyticsDto,
  ExperimentRunRowDto,
  ExperimentDetailDto,
  ExperimentRunRequest,
  run_experiment_experiments__experiment_id__run_post_Body,
  ExperimentRunResult,
  SubmitRequest,
  BatchStatus,
  SubmitResponse,
  WeightSyncRequest,
  WeightSyncResponse,
  EpisodeFailure,
  Trajectory,
  PollResponse,
  definition_id,
  TrainingCurvePointDto,
  TrainingSessionDto,
  TrainingMetricDto,
  RunContextEventDto,
  RunEvaluationCriterionDto,
  RunTaskEvaluationDto,
  RunExecutionAttemptDto,
  RunResourceDto,
  RunSandboxCommandDto,
  RunSandboxDto,
  RunTaskDto,
  RunCommunicationMessageDto,
  RunCommunicationThreadDto,
  RunSnapshotDto,
  NodeAddedMutation,
  NodeRemovedMutation,
  NodeStatusChangedMutation,
  NodeFieldChangedMutation,
  EdgeAddedMutation,
  EdgeRemovedMutation,
  EdgeStatusChangedMutation,
  JsonValue_Output,
  JsonObject_Output,
  AnnotationSetMutation,
  AnnotationDeletedMutation,
  RunGraphMutationDto,
};
