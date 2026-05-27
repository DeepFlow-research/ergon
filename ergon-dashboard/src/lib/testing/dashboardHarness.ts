import {
  broadcastContextEvent,
  broadcastSampleCompleted,
  broadcastTaskEvaluation,
  broadcastTaskStatus,
  broadcastThreadMessage,
} from "@/lib/socket/server";
import { config } from "@/lib/config";
import { store } from "@/lib/state/store";
import {
  CommunicationThreadState,
  ContextEventState,
  SampleDashboardState,
  SerializedSampleWorkspaceState,
  TaskEvaluationState,
  TaskStatus,
} from "@/lib/types";
import { deserializeSampleState, serializeSampleState } from "@/lib/sampleState";

declare global {
  // eslint-disable-next-line no-var
  var __dashboardHarness:
    | {
        experimentDetails: Record<string, unknown>;
        sampleStates: Record<string, SampleDashboardState>;
        mutationsBySample: Record<string, unknown[]>;
        seededSampleIds: Set<string>;
      }
    | undefined;
}

export interface DashboardHarnessSeedPayload {
  experimentDetails?: Record<string, unknown>;
  sampleStates?: Record<string, SampleDashboardState>;
  runs?: SerializedSampleWorkspaceState[];
  mutations?: Record<string, unknown[]>;
}

function getHarnessState() {
  if (!global.__dashboardHarness) {
    global.__dashboardHarness = {
      experimentDetails: {},
      sampleStates: {},
      mutationsBySample: {},
      seededSampleIds: new Set(),
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
  harness.sampleStates = {};
  harness.mutationsBySample = {};
  harness.seededSampleIds.clear();
}

export function seedDashboardHarness(payload: DashboardHarnessSeedPayload): void {
  requireHarnessEnabled();
  resetDashboardHarness();

  const harness = getHarnessState();
  harness.experimentDetails = payload.experimentDetails ?? {};
  harness.sampleStates = payload.sampleStates ?? {};
  harness.mutationsBySample = payload.mutations ?? {};

  for (const run of payload.runs ?? []) {
    store.seedSample(deserializeSampleState(run));
    harness.seededSampleIds.add(run.id);
  }
}

export function getHarnessExperiment(experimentId: string): unknown | null {
  requireHarnessEnabled();
  return getHarnessState().experimentDetails[experimentId] ?? null;
}

export function getHarnessSampleState(sampleId: string): SampleDashboardState | null {
  requireHarnessEnabled();
  return getHarnessState().sampleStates[sampleId] ?? null;
}

export function getHarnessSample(sampleId: string): SerializedSampleWorkspaceState | null {
  requireHarnessEnabled();
  if (!getHarnessState().seededSampleIds.has(sampleId)) {
    return null;
  }
  const run = store.getSample(sampleId);
  return run ? serializeSampleState(run) : null;
}

export function getHarnessSampleMutations(sampleId: string): unknown[] | null {
  requireHarnessEnabled();
  return getHarnessState().mutationsBySample[sampleId] ?? null;
}

export function emitHarnessSampleCompleted(data: {
  sampleId: string;
  status: "completed" | "failed";
  durationSeconds: number;
  finalScore: number | null;
  error: string | null;
}): void {
  requireHarnessEnabled();
  store.completeSample(
    data.sampleId,
    data.status,
    new Date().toISOString(),
    data.durationSeconds,
    data.finalScore,
    data.error,
  );
  broadcastSampleCompleted(
    data.sampleId,
    data.status,
    new Date().toISOString(),
    data.durationSeconds,
    data.finalScore,
    data.error,
  );

}

export function emitHarnessTaskStatus(data: {
  sampleId: string;
  taskId: string;
  status: TaskStatus;
  assignedWorkerId?: string | null;
  assignedWorkerName?: string | null;
}): void {
  requireHarnessEnabled();
  store.updateTaskStatus(
    data.sampleId,
    data.taskId,
    data.status,
    new Date().toISOString(),
    data.assignedWorkerId,
    data.assignedWorkerName,
  );
  broadcastTaskStatus(
    data.sampleId,
    data.taskId,
    data.status,
    new Date().toISOString(),
    data.assignedWorkerId ?? null,
    data.assignedWorkerName ?? null,
  );
}

export function emitHarnessThreadMessage(sampleId: string, thread: CommunicationThreadState): void {
  requireHarnessEnabled();
  store.upsertThread(sampleId, thread);
  const messages = thread.messages ?? [];
  const message = messages[messages.length - 1];
  if (message) {
    broadcastThreadMessage({
      sample_id: sampleId,
      thread,
      message,
    });
  }
}

export function emitHarnessContextEvent(
  sampleId: string,
  taskId: string,
  event: ContextEventState,
): void {
  requireHarnessEnabled();
  store.addContextEvent(sampleId, taskId, event);
  broadcastContextEvent(sampleId, taskId, event);
}

export function emitHarnessTaskEvaluation(
  sampleId: string,
  taskId: string | null,
  evaluation: TaskEvaluationState,
): void {
  requireHarnessEnabled();
  store.upsertEvaluation(sampleId, taskId, evaluation);
  broadcastTaskEvaluation({
    sample_id: sampleId,
    task_id: taskId,
    evaluation,
  });
}
