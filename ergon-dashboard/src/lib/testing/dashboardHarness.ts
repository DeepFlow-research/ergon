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
  ExperimentDetail,
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
        experimentDetails: Record<string, ExperimentDetail>;
        mutationsByRun: Record<string, unknown[]>;
      }
    | undefined;
}

export interface DashboardHarnessSeedPayload {
  cohorts?: CohortSummary[];
  cohortDetails?: Record<string, CohortDetail>;
  experimentDetails?: Record<string, ExperimentDetail>;
  runs?: SerializedWorkflowRunState[];
  mutations?: Record<string, unknown[]>;
}

function getHarnessState() {
  if (!global.__dashboardHarness) {
    global.__dashboardHarness = {
      cohorts: [],
      cohortDetails: {},
      experimentDetails: {},
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
  harness.experimentDetails = {};
  harness.mutationsByRun = {};
}

export function seedDashboardHarness(payload: DashboardHarnessSeedPayload): void {
  requireHarnessEnabled();
  resetDashboardHarness();

  const harness = getHarnessState();
  harness.cohorts = payload.cohorts ?? [];
  harness.cohortDetails = payload.cohortDetails ?? {};
  harness.experimentDetails = payload.experimentDetails ?? {};
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

export function getHarnessExperiment(experimentId: string): ExperimentDetail | null {
  requireHarnessEnabled();
  return getHarnessState().experimentDetails[experimentId] ?? null;
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
      const summary: CohortSummary = {
        ...detail.summary,
        total_runs: detail.summary.total_runs,
        status_counts: {
          ...detail.summary.status_counts,
          completed:
            data.status === "completed"
              ? detail.summary.status_counts.completed + 1
              : detail.summary.status_counts.completed,
          failed:
            data.status === "failed"
              ? detail.summary.status_counts.failed + 1
              : detail.summary.status_counts.failed,
        },
      };
      const updatedDetail: CohortDetail = {
        ...detail,
        summary,
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
