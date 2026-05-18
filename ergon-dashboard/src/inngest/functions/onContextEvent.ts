import { inngest } from "../client";
import { parseDashboardContextEventData } from "@/lib/contracts/events";
import { store } from "@/lib/state/store";
import { broadcastContextEvent } from "@/lib/socket/server";
import type { ContextEventState } from "@/lib/types";

export const onContextEvent = inngest.createFunction(
  { id: "dashboard-context-event" },
  { event: "dashboard/context.event" },
  async ({ event }) => {
    const payload = parseDashboardContextEventData(event.data);

    const contextEvent: ContextEventState = {
      id: payload.id,
      runId: payload.run_id,
      taskExecutionId: payload.task_execution_id,
      taskId: payload.task_id,
      workerBindingKey: payload.worker_binding_key,
      sequence: payload.sequence,
      eventType: payload.event_type as ContextEventState["eventType"],
      payload: payload.payload as ContextEventState["payload"],
      createdAt: payload.created_at,
      startedAt: payload.started_at ?? null,
      completedAt: payload.completed_at ?? null,
    };

    store.addContextEvent(payload.run_id, payload.task_id, contextEvent);
    broadcastContextEvent(payload.run_id, payload.task_id, contextEvent);

    return { success: true };
  },
);
