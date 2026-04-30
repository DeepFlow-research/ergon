import type { SerializedWorkflowRunState, WorkflowRunState } from "@/lib/types";

import { serializeContextEvent } from "./contextEvents";

export function serializeRunSnapshot(run: WorkflowRunState): SerializedWorkflowRunState {
  return {
    ...run,
    tasks: Object.fromEntries(run.tasks.entries()),
    resourcesByTask: Object.fromEntries(run.resourcesByTask.entries()),
    executionsByTask: Object.fromEntries(run.executionsByTask.entries()),
    sandboxesByTask: Object.fromEntries(run.sandboxesByTask.entries()),
    evaluationsByTask: Object.fromEntries(run.evaluationsByTask.entries()),
    contextEventsByTask: Object.fromEntries(
      Array.from(run.contextEventsByTask.entries()).map(([taskId, events]) => [
        taskId,
        events.map(serializeContextEvent),
      ]),
    ),
  } as unknown as SerializedWorkflowRunState;
}

export const serializeRunState = serializeRunSnapshot;
