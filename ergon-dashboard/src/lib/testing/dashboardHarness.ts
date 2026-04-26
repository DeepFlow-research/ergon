import {
  broadcastCohortUpdated,
  broadcastContextEvent,
  broadcastRunCompleted,
  broadcastTaskEvaluation,
  broadcastTaskStatus,
  broadcastThreadMessage,
} from "@/lib/socket/server";
import { config } from "@/lib/config";
import { store } from "@/lib/state/store";
import {
  CommunicationThreadState,
  CohortDetail,
  CohortSummary,
  ContextEventState,
  ExperimentCohortStatus,
  SerializedWorkflowRunState,
  TaskEvaluationState,
  TaskStatus,
} from "@/lib/types";
import { deserializeRunState, serializeRunState } from "@/lib/runState";

declare global {
  // eslint-disable-next-line no-var
  var __dashboardHarness:
    | {
        cohorts: CohortSummary[];
        cohortDetails: Record<string, CohortDetail>;
        mutationsByRun: Record<string, unknown[]>;
      }
    | undefined;
}

export interface DashboardHarnessSeedPayload {
  cohorts?: CohortSummary[];
  cohortDetails?: Record<string, CohortDetail>;
  runs?: SerializedWorkflowRunState[];
  mutations?: Record<string, unknown[]>;
}

function getHarnessState() {
  if (!global.__dashboardHarness) {
    global.__dashboardHarness = {
      cohorts: [],
      cohortDetails: {},
      mutationsByRun: {},
    };
  }
  return global.__dashboardHarness;
}

function requireHarnessEnabled() {
  if (!config.enableTestHarness) {
    throw new Error("Dashboard test harness is disabled");
  }
}

export function resetDashboardHarness(): void {
  requireHarnessEnabled();
  store.reset();
  const harness = getHarnessState();
  harness.cohorts = [];
  harness.cohortDetails = {};
  harness.mutationsByRun = {};
}

export function seedDashboardHarness(payload: DashboardHarnessSeedPayload): void {
  requireHarnessEnabled();
  resetDashboardHarness();

  const harness = getHarnessState();
  harness.cohorts = payload.cohorts ?? [];
  harness.cohortDetails = payload.cohortDetails ?? {};
  harness.mutationsByRun = payload.mutations ?? {};

  for (const run of payload.runs ?? []) {
    store.seedRun(deserializeRunState(run));
  }
}

export function listHarnessCohorts(): CohortSummary[] {
  requireHarnessEnabled();
  return getHarnessState().cohorts;
}

export function getHarnessCohort(cohortId: string): CohortDetail | null {
  requireHarnessEnabled();
  return getHarnessState().cohortDetails[cohortId] ?? null;
}

export function updateHarnessCohortStatus(
  cohortId: string,
  status: ExperimentCohortStatus,
): CohortSummary | null {
  requireHarnessEnabled();
  const harness = getHarnessState();
  const summary = harness.cohorts.find((cohort) => cohort.cohort_id === cohortId);
  if (!summary) {
    return null;
  }

  const updatedSummary: CohortSummary = {
    ...summary,
    status,
  };
  harness.cohorts = harness.cohorts.map((cohort) =>
    cohort.cohort_id === cohortId ? updatedSummary : cohort,
  );

  const detail = harness.cohortDetails[cohortId];
  if (detail) {
    harness.cohortDetails[cohortId] = {
      ...detail,
      summary: updatedSummary,
    };
  }

  broadcastCohortUpdated({ cohort_id: cohortId, summary: updatedSummary });
  return updatedSummary;
}

export function getHarnessRun(runId: string): SerializedWorkflowRunState | null {
  requireHarnessEnabled();
  const run = store.getRun(runId);
  return run ? serializeRunState(run) : null;
}

export function getHarnessRunMutations(runId: string): unknown[] | null {
  requireHarnessEnabled();
  return getHarnessState().mutationsByRun[runId] ?? null;
}

export function emitHarnessRunCompleted(data: {
  runId: string;
  status: "completed" | "failed";
  durationSeconds: number;
  finalScore: number | null;
  error: string | null;
  cohortId?: string | null;
}): void {
  requireHarnessEnabled();
  store.completeRun(
    data.runId,
    data.status,
    new Date().toISOString(),
    data.durationSeconds,
    data.finalScore,
    data.error,
  );
  broadcastRunCompleted(
    data.runId,
    data.status,
    new Date().toISOString(),
    data.durationSeconds,
    data.finalScore,
    data.error,
  );

  if (data.cohortId) {
    const harness = getHarnessState();
    const detail = harness.cohortDetails[data.cohortId];
    if (detail) {
      const updatedRuns = (detail.runs ?? []).map((run) =>
        run.run_id === data.runId
          ? {
              ...run,
              status: data.status,
              final_score: data.finalScore,
              error_message: data.error,
              completed_at: new Date().toISOString(),
              running_time_ms: data.durationSeconds * 1000,
            }
          : run,
      );
      const completed = updatedRuns.filter((run) => run.status === "completed").length;
      const failed = updatedRuns.filter((run) => run.status === "failed").length;
      const executing = updatedRuns.filter((run) => run.status === "executing").length;
      const pending = updatedRuns.filter((run) => run.status === "pending").length;
      const evaluating = updatedRuns.filter((run) => run.status === "evaluating").length;
      const summary: CohortSummary = {
        ...detail.summary,
        total_runs: updatedRuns.length,
        status_counts: {
          pending,
          executing,
          evaluating,
          completed,
          failed,
        },
      };
      const updatedDetail: CohortDetail = {
        summary,
        runs: updatedRuns,
      };
      harness.cohortDetails[data.cohortId] = updatedDetail;
      harness.cohorts = harness.cohorts.map((cohort) =>
        cohort.cohort_id === data.cohortId ? summary : cohort,
      );
      broadcastCohortUpdated({ cohort_id: data.cohortId, summary });
    }
  }
}

export function emitHarnessTaskStatus(data: {
  runId: string;
  taskId: string;
  status: TaskStatus;
  assignedWorkerId?: string | null;
  assignedWorkerName?: string | null;
}): void {
  requireHarnessEnabled();
  store.updateTaskStatus(
    data.runId,
    data.taskId,
    data.status,
    new Date().toISOString(),
    data.assignedWorkerId,
    data.assignedWorkerName,
  );
  broadcastTaskStatus(
    data.runId,
    data.taskId,
    data.status,
    new Date().toISOString(),
    data.assignedWorkerId ?? null,
    data.assignedWorkerName ?? null,
  );
}

export function emitHarnessThreadMessage(runId: string, thread: CommunicationThreadState): void {
  requireHarnessEnabled();
  store.upsertThread(runId, thread);
  const messages = thread.messages ?? [];
  const message = messages[messages.length - 1];
  if (message) {
    broadcastThreadMessage({
      run_id: runId,
      thread,
      message,
    });
  }
}

export function emitHarnessContextEvent(
  runId: string,
  taskNodeId: string,
  event: ContextEventState,
): void {
  requireHarnessEnabled();
  store.addContextEvent(runId, taskNodeId, event);
  broadcastContextEvent(runId, taskNodeId, event);
}

export function emitHarnessTaskEvaluation(
  runId: string,
  taskId: string | null,
  evaluation: TaskEvaluationState,
): void {
  requireHarnessEnabled();
  store.upsertEvaluation(runId, taskId, evaluation);
  broadcastTaskEvaluation({
    run_id: runId,
    task_id: taskId,
    evaluation,
  });
}
