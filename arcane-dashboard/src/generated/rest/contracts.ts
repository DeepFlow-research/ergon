import { z } from "zod";

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
  assignedWorkerName: z.union([z.string(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
});
const RunActionDto = z.object({
  id: z.string(),
  taskId: z.string(),
  workerId: z.string(),
  workerName: z.string(),
  type: z.string(),
  input: z.string(),
  output: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
  success: z.boolean(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
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
  outputText: z.union([z.string(), z.null()]).optional(),
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
  criterionType: z.string(),
  criterionDescription: z.string(),
  evaluationInput: z.string(),
  score: z.number(),
  maxScore: z.number(),
  feedback: z.string(),
  evaluatedActionIds: z.array(z.string()).optional(),
  evaluatedResourceIds: z.array(z.string()).optional(),
  error: z.union([z.object({}).partial().passthrough(), z.null()]).optional(),
});
const RunTaskEvaluationDto = z.object({
  id: z.string(),
  runId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
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
const RunCommunicationMessageDto = z.object({
  id: z.string(),
  threadId: z.string(),
  threadTopic: z.string(),
  runId: z.string(),
  taskId: z.union([z.string(), z.null()]).optional(),
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
  actionsByTask: z.record(z.string(), z.array(RunActionDto)).optional(),
  resourcesByTask: z.record(z.string(), z.array(RunResourceDto)).optional(),
  executionsByTask: z.record(z.string(), z.array(RunExecutionAttemptDto)).optional(),
  evaluationsByTask: z.record(z.string(), RunTaskEvaluationDto).optional(),
  sandboxesByTask: z.record(z.string(), RunSandboxDto).optional(),
  threads: z.array(RunCommunicationThreadDto).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  durationSeconds: z.union([z.number(), z.null()]).optional(),
  totalTasks: z.number().int().optional().default(0),
  totalLeafTasks: z.number().int().optional().default(0),
  completedTasks: z.number().int().optional().default(0),
  failedTasks: z.number().int().optional().default(0),
  runningTasks: z.number().int().optional().default(0),
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
const CohortRunRowDto = z
  .object({
    run_id: z.string().uuid(),
    definition_id: z.string().uuid(),
    cohort_id: z.string().uuid(),
    cohort_name: z.string(),
    status: z.string(),
    created_at: z.string().datetime({ offset: true }),
    started_at: z.union([z.string(), z.null()]).optional(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    running_time_ms: z.union([z.number(), z.null()]).optional(),
    final_score: z.union([z.number(), z.null()]).optional(),
    error_message: z.union([z.string(), z.null()]).optional(),
  })
  .passthrough();
const CohortDetailDto = z
  .object({
    summary: CohortSummaryDto,
    runs: z.array(CohortRunRowDto).optional(),
  })
  .passthrough();
const ExperimentCohortStatus = z.enum(["active", "archived"]);
const UpdateCohortRequest = z
  .object({ status: ExperimentCohortStatus })
  .passthrough();

const BenchmarkName = z.enum(["gdpeval", "minif2f", "researchrubrics", "custom", "smoke_test"]);
const RunStatus = z.enum(["pending", "executing", "evaluating", "completed", "failed"]);
const TaskStatus = z.enum(["pending", "ready", "running", "completed", "failed"]);

const DispatchConfigSnapshot = z
  .object({
    extras: z.object({}).partial().passthrough(),
    max_concurrent_runs: z.union([z.number(), z.null()]),
    max_questions: z.union([z.number(), z.null()]),
    max_retries: z.union([z.number(), z.null()]),
    worker_model: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
const SandboxConfigSnapshot = z
  .object({
    extras: z.object({}).partial().passthrough(),
    provider: z.union([z.string(), z.null()]),
    template_id: z.union([z.string(), z.null()]),
    timeout_minutes: z.union([z.number(), z.null()]),
  })
  .partial()
  .passthrough();
const CohortMetadataSummaryDto = z
  .object({
    code_commit_sha: z.union([z.string(), z.null()]),
    dispatch_config: DispatchConfigSnapshot,
    model_name: z.union([z.string(), z.null()]),
    model_provider: z.union([z.string(), z.null()]),
    prompt_version: z.union([z.string(), z.null()]),
    repo_dirty: z.union([z.boolean(), z.null()]),
    sandbox_config: SandboxConfigSnapshot,
    worker_version: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
const CohortStatsExtras = z
  .object({
    benchmark_counts: z.record(z.string(), z.number().int()),
    latest_run_at: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();

export const schemas = {
  BenchmarkName,
  RunStatus,
  TaskStatus,
  DispatchConfigSnapshot,
  SandboxConfigSnapshot,
  CohortMetadataSummaryDto,
  CohortStatsExtras,
  RunTaskDto,
  RunActionDto,
  RunResourceDto,
  RunExecutionAttemptDto,
  RunEvaluationCriterionDto,
  RunTaskEvaluationDto,
  RunSandboxCommandDto,
  RunSandboxDto,
  RunCommunicationMessageDto,
  RunCommunicationThreadDto,
  RunSnapshotDto,
  ValidationError,
  HTTPValidationError,
  CohortStatusCountsDto,
  CohortSummaryDto,
  CohortRunRowDto,
  CohortDetailDto,
  ExperimentCohortStatus,
  UpdateCohortRequest,
};
