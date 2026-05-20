import {
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
  ContextEventState,
  ExperimentDetail,
  SerializedWorkflowRunState,
  TaskEvaluationState,
  TaskStatus,
} from "@/lib/types";
import { deserializeRunState, serializeRunState } from "@/lib/runState";

declare global {
  // eslint-disable-next-line no-var
  var __dashboardHarness:
    | {
        experimentDetails: Record<string, ExperimentDetail>;
        mutationsByRun: Record<string, unknown[]>;
        seededRunIds: Set<string>;
      }
    | undefined;
}

export interface DashboardHarnessSeedPayload {
  experimentDetails?: Record<string, ExperimentDetail>;
  runs?: SerializedWorkflowRunState[];
  mutations?: Record<string, unknown[]>;
}

function getHarnessState() {
  if (!global.__dashboardHarness) {
    global.__dashboardHarness = {
      experimentDetails: {},
      mutationsByRun: {},
      seededRunIds: new Set(),
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
  harness.experimentDetails = {};
  harness.mutationsByRun = {};
  harness.seededRunIds.clear();
}

export function seedDashboardHarness(payload: DashboardHarnessSeedPayload): void {
  requireHarnessEnabled();
  resetDashboardHarness();

  const harness = getHarnessState();
  harness.experimentDetails = payload.experimentDetails ?? {};
  harness.mutationsByRun = payload.mutations ?? {};

  for (const run of payload.runs ?? []) {
    store.seedRun(deserializeRunState(run));
    harness.seededRunIds.add(run.id);
  }
}

export function getHarnessExperiment(definitionId: string): ExperimentDetail | null {
  requireHarnessEnabled();
  return getHarnessState().experimentDetails[definitionId] ?? null;
}

export function getHarnessRun(runId: string): SerializedWorkflowRunState | null {
  requireHarnessEnabled();
  if (!getHarnessState().seededRunIds.has(runId)) {
    return null;
  }
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
  taskId: string,
  event: ContextEventState,
): void {
  requireHarnessEnabled();
  store.addContextEvent(runId, taskId, event);
  broadcastContextEvent(runId, taskId, event);
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
