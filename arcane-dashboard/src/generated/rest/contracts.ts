import { z } from "zod";

const CohortStatsExtras = z
  .object({
    benchmark_counts: z.record(z.number().int()),
    latest_run_at: z.union([z.string(), z.null()]),
  })
  .partial()
  .passthrough();
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
const ExperimentCohortStatus = z.enum(["active", "archived"]);
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
    extras: CohortStatsExtras.optional(),
    failure_rate: z.number().optional().default(0),
    metadata_summary: CohortMetadataSummaryDto.optional(),
    name: z.string(),
    stats_updated_at: z.union([z.string(), z.null()]).optional(),
    status: ExperimentCohortStatus,
    status_counts: CohortStatusCountsDto.optional(),
    total_runs: z.number().int().optional().default(0),
    worst_score: z.union([z.number(), z.null()]).optional(),
  })
  .passthrough();
const ValidationError = z
  .object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
  })
  .passthrough();
const HTTPValidationError = z
  .object({ detail: z.array(ValidationError) })
  .partial()
  .passthrough();
const BenchmarkName = z.enum([
  "gdpeval",
  "minif2f",
  "researchrubrics",
  "custom",
  "smoke_test",
]);
const RunStatus = z.enum([
  "pending",
  "executing",
  "evaluating",
  "completed",
  "failed",
]);
const CohortRunRowDto = z
  .object({
    benchmark_name: BenchmarkName,
    cohort_id: z.string().uuid(),
    cohort_name: z.string(),
    completed_at: z.union([z.string(), z.null()]).optional(),
    created_at: z.string().datetime({ offset: true }),
    error_message: z.union([z.string(), z.null()]).optional(),
    experiment_id: z.string().uuid(),
    experiment_task_id: z.string(),
    final_score: z.union([z.number(), z.null()]).optional(),
    max_questions: z.number().int(),
    normalized_score: z.union([z.number(), z.null()]).optional(),
    run_id: z.string().uuid(),
    running_time_ms: z.union([z.number(), z.null()]).optional(),
    started_at: z.union([z.string(), z.null()]).optional(),
    status: RunStatus,
    worker_model: z.string(),
    workflow_name: z.string(),
  })
  .passthrough();
const CohortDetailDto = z
  .object({
    runs: z.array(CohortRunRowDto).optional(),
    summary: CohortSummaryDto,
  })
  .passthrough();
const UpdateCohortRequest = z
  .object({ status: ExperimentCohortStatus })
  .passthrough();
const RunActionDto = z.object({
  completedAt: z.union([z.string(), z.null()]).optional(),
  durationMs: z.union([z.number(), z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
  id: z.string(),
  input: z.string(),
  output: z.union([z.string(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: z.string(),
  success: z.boolean(),
  taskId: z.string(),
  type: z.string(),
  workerId: z.string(),
  workerName: z.string(),
});
const RunEvaluationCriterionDto = z.object({
  criterionDescription: z.string(),
  criterionNum: z.number().int(),
  criterionType: z.string(),
  error: z.union([z.object({}).partial().passthrough(), z.null()]).optional(),
  evaluatedActionIds: z.array(z.string()).optional(),
  evaluatedResourceIds: z.array(z.string()).optional(),
  evaluationInput: z.string(),
  feedback: z.string(),
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
const TaskStatus = z.enum([
  "pending",
  "ready",
  "running",
  "completed",
  "failed",
]);
const RunExecutionAttemptDto = z.object({
  agentId: z.union([z.string(), z.null()]).optional(),
  agentName: z.union([z.string(), z.null()]).optional(),
  attemptNumber: z.number().int(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  errorMessage: z.union([z.string(), z.null()]).optional(),
  evaluationDetails: z.object({}).partial().passthrough().optional(),
  id: z.string(),
  outputResourceIds: z.array(z.string()).optional(),
  outputText: z.union([z.string(), z.null()]).optional(),
  score: z.union([z.number(), z.null()]).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: TaskStatus,
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
  status: TaskStatus,
});
const RunCommunicationMessageDto = z.object({
  content: z.string(),
  createdAt: z.string().datetime({ offset: true }),
  fromAgentId: z.string(),
  id: z.string(),
  runId: z.string(),
  sequenceNum: z.number().int(),
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
  taskId: z.union([z.string(), z.null()]).optional(),
  topic: z.string(),
  updatedAt: z.string().datetime({ offset: true }),
});
const RunSnapshotDto = z.object({
  actionsByTask: z.record(z.array(RunActionDto)).optional(),
  completedAt: z.union([z.string(), z.null()]).optional(),
  completedTasks: z.number().int().optional().default(0),
  durationSeconds: z.union([z.number(), z.null()]).optional(),
  error: z.union([z.string(), z.null()]).optional(),
  evaluationsByTask: z.record(RunTaskEvaluationDto).optional(),
  executionsByTask: z.record(z.array(RunExecutionAttemptDto)).optional(),
  experimentId: z.string(),
  failedTasks: z.number().int().optional().default(0),
  finalScore: z.union([z.number(), z.null()]).optional(),
  id: z.string(),
  name: z.string(),
  resourcesByTask: z.record(z.array(RunResourceDto)).optional(),
  rootTaskId: z.string().optional().default(""),
  runningTasks: z.number().int().optional().default(0),
  sandboxesByTask: z.record(RunSandboxDto).optional(),
  startedAt: z.union([z.string(), z.null()]).optional(),
  status: RunStatus,
  tasks: z.record(RunTaskDto).optional(),
  threads: z.array(RunCommunicationThreadDto).optional(),
  totalLeafTasks: z.number().int().optional().default(0),
  totalTasks: z.number().int().optional().default(0),
});

export const schemas = {
  CohortStatsExtras,
  DispatchConfigSnapshot,
  SandboxConfigSnapshot,
  CohortMetadataSummaryDto,
  ExperimentCohortStatus,
  CohortStatusCountsDto,
  CohortSummaryDto,
  ValidationError,
  HTTPValidationError,
  BenchmarkName,
  RunStatus,
  CohortRunRowDto,
  CohortDetailDto,
  UpdateCohortRequest,
  RunActionDto,
  RunEvaluationCriterionDto,
  RunTaskEvaluationDto,
  TaskStatus,
  RunExecutionAttemptDto,
  RunResourceDto,
  RunSandboxCommandDto,
  RunSandboxDto,
  RunTaskDto,
  RunCommunicationMessageDto,
  RunCommunicationThreadDto,
  RunSnapshotDto,
};
