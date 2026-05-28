/* eslint-disable @typescript-eslint/no-empty-object-type */
import { z } from "zod";

type JsonValue =
  | (JsonScalar | Array<JsonValue> | {})
  | Array<JsonScalar | Array<JsonValue> | {}>;
type JsonScalar =
  | (string | number | number | boolean | null)
  | Array<string | number | number | boolean | null>;

const status = z.union([z.string(), z.null()]).optional();
const SampleSummaryDto = z
  .object({
    id: z.string().uuid(),
    name: z.string(),
    status: z.string(),
    created_at: z.union([z.string(), z.null()]).optional(),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    latest_activity_at: z.union([z.string(), z.null()]).optional(),
    duration_seconds: z.union([z.number(), z.null()]).optional(),
    experiment_id: z.union([z.string(), z.null()]).optional(),
    experiment: z.union([z.string(), z.null()]).optional(),
    benchmark_type: z.string(),
    instance_key: z.string(),
    sample_id: z.union([z.string(), z.null()]).optional(),
    sample_label: z.string(),
    evaluator_slug: z.union([z.string(), z.null()]).optional(),
    model_target: z.union([z.string(), z.null()]).optional(),
    final_score: z.union([z.number(), z.null()]).optional(),
    return: z.union([z.number(), z.null()]).optional(),
    total_tasks: z.number().int().optional().default(0),
    completed_tasks: z.number().int().optional().default(0),
    failed_tasks: z.number().int().optional().default(0),
    running_tasks: z.number().int().optional().default(0),
    cancelled_tasks: z.number().int().optional().default(0),
    total_cost_usd: z.union([z.number(), z.null()]).optional(),
    error_message: z.union([z.string(), z.null()]).optional(),
    metrics: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
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
const SampleTaskDto = z.object({
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
const SampleResourceDto = z.object({
  id: z.string(),
  taskId: z.string(),
  taskAttemptId: z.string(),
  name: z.string(),
  mimeType: z.string(),
  filePath: z.string(),
  sizeBytes: z.number().int(),
  createdAt: z.string().datetime({ offset: true }),
});
const SampleExecutionAttemptDto = z.object({
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
const SampleEvaluationCriterionDto = z.object({
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
const SampleTaskEvaluationDto = z.object({
  id: z.string(),
  sampleId: z.string(),
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
  criterionResults: z.array(SampleEvaluationCriterionDto).optional(),
});
const SampleSandboxCommandDto = z.object({
  command: z.string(),
  stdout: z.union([z.string(), z.null()]).optional(),
  stderr: z.union([z.string(), z.null()]).optional(),
  exitCode: z.union([z.number(), z.null()]).optional(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  timestamp: z.string().datetime({ offset: true }),
});
const SampleSandboxDto = z.object({
  sandboxId: z.string(),
  taskId: z.string(),
  template: z.union([z.string(), z.null()]).optional(),
  timeoutMinutes: z.number().int(),
  status: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  closedAt: z.union([z.string(), z.null()]).optional(),
  closeReason: z.union([z.string(), z.null()]).optional(),
  commands: z.array(SampleSandboxCommandDto).optional(),
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
const JsonValue: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([JsonScalar, z.array(JsonValue), z.record(z.string(), JsonValue)])
);
const JsonObject = z.record(z.string(), JsonValue);
const TokenLogprob = z
  .object({
    token: z.string(),
    logprob: z.number(),
    top_logprobs: z.array(JsonObject).optional(),
  })
  .passthrough();
const ProviderTokenUsage = z
  .object({
    prompt_tokens: z.union([z.number(), z.null()]),
    completion_tokens: z.union([z.number(), z.null()]),
    reasoning_tokens: z.union([z.number(), z.null()]),
    tool_call_tokens: z.union([z.number(), z.null()]),
    tool_result_tokens: z.union([z.number(), z.null()]),
    cached_tokens: z.union([z.number(), z.null()]),
    total_tokens: z.union([z.number(), z.null()]),
    total_cost_usd: z.union([z.number(), z.null()]),
  })
  .partial()
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
    provider_usage: z.union([ProviderTokenUsage, z.null()]).optional(),
    sequence: z.number().int(),
    worker_binding_key: z.string(),
    turn_id: z.union([z.string(), z.null()]).optional(),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    policy_version: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const SampleContextEventDto = z.object({
  id: z.string().uuid(),
  sampleId: z.string().uuid(),
  taskAttemptId: z.string().uuid(),
  taskId: z.string().uuid(),
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
const SampleCommunicationMessageDto = z.object({
  id: z.string(),
  threadId: z.string(),
  threadTopic: z.string(),
  sampleId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
  taskAttemptId: z.union([z.string(), z.null()]).optional(),
  fromAgentId: z.string(),
  toAgentId: z.string(),
  content: z.string(),
  sequenceNum: z.number().int(),
  createdAt: z.string().datetime({ offset: true }),
});
const SampleCommunicationThreadDto = z.object({
  id: z.string(),
  sampleId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
  topic: z.string(),
  summary: z.union([z.string(), z.null()]).optional(),
  agentAId: z.string(),
  agentBId: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  updatedAt: z.string().datetime({ offset: true }),
  messages: z.array(SampleCommunicationMessageDto).optional(),
});
const SampleSnapshotMetricsDto = z.object({
  sampleId: z.string(),
  status: z.string(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  totalTasks: z.number().int().optional().default(0),
  toolCallCount: z.number().int().optional().default(0),
  totalTokens: z.union([z.number(), z.null()]).optional(),
  tokenBreakdown: z.record(z.string(), z.number().int()).optional(),
  totalCostUsd: z.union([z.number(), z.null()]).optional(),
  costObserved: z.boolean().optional().default(false),
});
const SampleSnapshotDto = z.object({
  id: z.string(),
  experimentId: z.union([z.string(), z.null()]).optional(),
  name: z.string(),
  status: z.string(),
  tasks: z.record(z.string(), SampleTaskDto).optional(),
  rootTaskId: z.string().optional().default(""),
  resourcesByTask: z.record(z.string(), z.array(SampleResourceDto)).optional(),
  executionsByTask: z.record(z.string(), z.array(SampleExecutionAttemptDto)).optional(),
  evaluationsByTask: z.record(z.string(), SampleTaskEvaluationDto).optional(),
  sandboxesByTask: z.record(z.string(), SampleSandboxDto).optional(),
  contextEventsByTask: z.record(z.string(), z.array(SampleContextEventDto)).optional(),
  threads: z.array(SampleCommunicationThreadDto).optional(),
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
  metrics: z.union([SampleSnapshotMetricsDto, z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
});
const SampleDetailView = z.object({
  sampleId: z.string().uuid(),
  experimentId: z.string().uuid(),
  environmentId: z.string().uuid(),
  environmentName: z.string(),
  sampleKey: z.string(),
  sampleRef: z.object({}).partial().passthrough().optional(),
  sourceMetadata: z.object({}).partial().passthrough().optional(),
  status: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
});
const SampleStatusChangedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("sample.status_changed"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    status: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleTaskAddedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("task.added"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    taskSlug: z.union([z.string(), z.null()]).optional(),
    status: z.union([z.string(), z.null()]).optional(),
    task: JsonObject.optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleTaskRemovedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("task.removed"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    taskSlug: z.union([z.string(), z.null()]).optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleTaskStatusChangedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("task.status_changed"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    taskSlug: z.union([z.string(), z.null()]).optional(),
    status: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleEdgeAddedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("edge.added"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    sourceTaskId: z.string().uuid(),
    targetTaskId: z.string().uuid(),
    status: z.union([z.string(), z.null()]).optional(),
    edge: JsonObject.optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleEdgeRemovedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("edge.removed"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    sourceTaskId: z.string().uuid(),
    targetTaskId: z.string().uuid(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleEdgeStatusChangedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("edge.status_changed"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    sourceTaskId: z.string().uuid(),
    targetTaskId: z.string().uuid(),
    status: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleWorkerAddedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("worker.added"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    workerSlug: z.string(),
    workerType: z.union([z.string(), z.null()]).optional(),
    modelTarget: z.union([z.string(), z.null()]).optional(),
    worker: JsonObject.optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleWorkerRemovedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("worker.removed"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    workerSlug: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleEvaluatorAddedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("evaluator.added"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    evaluatorSlug: z.string(),
    evaluatorType: z.union([z.string(), z.null()]).optional(),
    evaluator: JsonObject.optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleEvaluatorRemovedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("evaluator.removed"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    evaluatorSlug: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleSandboxAddedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("sandbox.added"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    sandboxSlug: z.string(),
    sandboxType: z.union([z.string(), z.null()]).optional(),
    sandbox: JsonObject.optional(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleSandboxRemovedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("sandbox.removed"),
    targetType: z.string(),
    targetId: z.union([z.string(), z.null()]).optional(),
    sandboxSlug: z.string(),
    actor: z.union([z.string(), z.null()]).optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleAnnotationSetEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("annotation.set"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    key: z.string(),
    value: JsonObject.optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleAnnotationUpdatedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("annotation.updated"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    key: z.string(),
    value: JsonObject.optional(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleAnnotationDeletedEventView = z
  .object({
    eventId: z.string().uuid(),
    sampleId: z.string().uuid(),
    timestamp: z.string().datetime({ offset: true }),
    eventType: z.literal("annotation.deleted"),
    targetType: z.string(),
    targetId: z.string().uuid(),
    key: z.string(),
    payload: JsonObject.optional(),
  })
  .passthrough();
const SampleRuntimeEventView = z.discriminatedUnion("eventType", [
  SampleStatusChangedEventView,
  SampleTaskAddedEventView,
  SampleTaskRemovedEventView,
  SampleTaskStatusChangedEventView,
  SampleEdgeAddedEventView,
  SampleEdgeRemovedEventView,
  SampleEdgeStatusChangedEventView,
  SampleWorkerAddedEventView,
  SampleWorkerRemovedEventView,
  SampleEvaluatorAddedEventView,
  SampleEvaluatorRemovedEventView,
  SampleSandboxAddedEventView,
  SampleSandboxRemovedEventView,
  SampleAnnotationSetEventView,
  SampleAnnotationUpdatedEventView,
  SampleAnnotationDeletedEventView,
]);
const SampleEventsView = z
  .object({
    items: z.array(
      z.discriminatedUnion("eventType", [
        SampleStatusChangedEventView,
        SampleTaskAddedEventView,
        SampleTaskRemovedEventView,
        SampleTaskStatusChangedEventView,
        SampleEdgeAddedEventView,
        SampleEdgeRemovedEventView,
        SampleEdgeStatusChangedEventView,
        SampleWorkerAddedEventView,
        SampleWorkerRemovedEventView,
        SampleEvaluatorAddedEventView,
        SampleEvaluatorRemovedEventView,
        SampleSandboxAddedEventView,
        SampleSandboxRemovedEventView,
        SampleAnnotationSetEventView,
        SampleAnnotationUpdatedEventView,
        SampleAnnotationDeletedEventView,
      ])
    ),
  })
  .partial();
const SampleGraphNodeView = z.object({
  taskId: z.string().uuid(),
  taskSlug: z.string(),
  description: z.string(),
  status: z.string(),
  parentTaskId: z.union([z.string(), z.null()]).optional(),
  level: z.number().int().optional().default(0),
  assignedWorkerSlug: z.union([z.string(), z.null()]).optional(),
  createdAt: z.string().datetime({ offset: true }),
  updatedAt: z.string().datetime({ offset: true }),
});
const SampleGraphEdgeView = z.object({
  edgeId: z.string().uuid(),
  sourceTaskId: z.string().uuid(),
  targetTaskId: z.string().uuid(),
  status: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  updatedAt: z.string().datetime({ offset: true }),
});
const SampleGraphView = z
  .object({
    nodes: z.array(SampleGraphNodeView),
    edges: z.array(SampleGraphEdgeView),
  })
  .partial();
const EnvironmentContributionView = z
  .object({
    environmentId: z.string().uuid(),
    environmentName: z.string(),
    sourceMode: z.string(),
    sampleCount: z.number().int(),
    selectedCount: z.number().int(),
    sourceMetadata: z.object({}).partial().passthrough().optional(),
  })
  .passthrough();
const ExperimentSampleSummaryView = z
  .object({
    sampleId: z.string().uuid(),
    experimentId: z.string().uuid(),
    environmentId: z.string().uuid(),
    environmentName: z.string(),
    sampleKey: z.string(),
    sampleRef: z.object({}).partial().passthrough().optional(),
    sourceMetadata: z.object({}).partial().passthrough().optional(),
    status: z.string(),
    createdAt: z.string().datetime({ offset: true }),
  })
  .passthrough();
const SamplerInvocationView = z
  .object({
    samplerInvocationId: z.string().uuid(),
    samplerName: z.string(),
    requestedK: z.number().int(),
    candidatePoolSize: z.number().int(),
    selectedCount: z.number().int(),
    samplerConfig: z.object({}).partial().passthrough().optional(),
    createdAt: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ExperimentDetailView = z
  .object({
    experimentId: z.string().uuid(),
    name: z.string(),
    description: z.union([z.string(), z.null()]).optional(),
    environments: z.array(EnvironmentContributionView).optional(),
    sampleCount: z.number().int(),
    samples: z.array(ExperimentSampleSummaryView).optional(),
    samplerInvocations: z.array(SamplerInvocationView).optional(),
    metadata: z.object({}).partial().passthrough().optional(),
    createdAt: z.string().datetime({ offset: true }),
  })
  .passthrough();
const ExperimentListView = z
  .object({ items: z.array(ExperimentDetailView) })
  .partial()
  .passthrough();
const ExperimentSamplesView = z
  .object({ items: z.array(ExperimentSampleSummaryView) })
  .partial()
  .passthrough();
const SamplerInvocationsView = z
  .object({ items: z.array(SamplerInvocationView) })
  .partial()
  .passthrough();
const TrainingRolloutRequest = z
  .object({
    experimentId: z.string().uuid(),
    k: z.number().int().gte(1),
    sampler: z.string().optional().default("random"),
    samplerConfig: z.object({}).partial().passthrough().optional(),
    candidatePoolSize: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const RolloutStatus = z.enum([
  "pending",
  "running",
  "complete",
  "failed",
  "cancelled",
]);
const RolloutBatchSummary = z
  .object({
    batchId: z.string().uuid(),
    sampleIds: z.array(z.string().uuid()),
    status: RolloutStatus,
    experimentId: z.union([z.string(), z.null()]).optional(),
    samplerInvocationId: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const Trajectory = z
  .object({
    sample_id: z.string().uuid(),
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
  .object({ sample_id: z.string().uuid(), error: z.string() })
  .passthrough();
const PollResponse = z
  .object({
    batch_id: z.string().uuid(),
    status: RolloutStatus,
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
  status,
  SampleSummaryDto,
  ValidationError,
  HTTPValidationError,
  SampleTaskDto,
  SampleResourceDto,
  SampleExecutionAttemptDto,
  SampleEvaluationCriterionDto,
  SampleTaskEvaluationDto,
  SampleSandboxCommandDto,
  SampleSandboxDto,
  SystemPromptPart,
  UserMessagePart,
  AssistantTextPart,
  ToolCallPart,
  ToolResultPart,
  ThinkingPart,
  JsonScalar,
  JsonValue,
  JsonObject,
  TokenLogprob,
  ProviderTokenUsage,
  ContextPartChunkLog,
  SampleContextEventDto,
  SampleCommunicationMessageDto,
  SampleCommunicationThreadDto,
  SampleSnapshotMetricsDto,
  SampleSnapshotDto,
  SampleDetailView,
  SampleStatusChangedEventView,
  SampleTaskAddedEventView,
  SampleTaskRemovedEventView,
  SampleTaskStatusChangedEventView,
  SampleEdgeAddedEventView,
  SampleEdgeRemovedEventView,
  SampleEdgeStatusChangedEventView,
  SampleWorkerAddedEventView,
  SampleWorkerRemovedEventView,
  SampleEvaluatorAddedEventView,
  SampleEvaluatorRemovedEventView,
  SampleSandboxAddedEventView,
  SampleSandboxRemovedEventView,
  SampleAnnotationSetEventView,
  SampleAnnotationUpdatedEventView,
  SampleAnnotationDeletedEventView,
  SampleRuntimeEventView,
  SampleEventsView,
  SampleGraphNodeView,
  SampleGraphEdgeView,
  SampleGraphView,
  EnvironmentContributionView,
  ExperimentSampleSummaryView,
  SamplerInvocationView,
  ExperimentDetailView,
  ExperimentListView,
  ExperimentSamplesView,
  SamplerInvocationsView,
  TrainingRolloutRequest,
  RolloutStatus,
  RolloutBatchSummary,
  Trajectory,
  EpisodeFailure,
  PollResponse,
  WeightSyncRequest,
  WeightSyncResponse,
};
