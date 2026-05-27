import type { SampleRuntimeEventView } from "@/lib/contracts/rest";

import type { MutationType, SampleGraphEventDto } from "./contracts/graphMutations";

function graphMutationType(eventType: string): MutationType | null {
  switch (eventType) {
    case "task.added":
      return "node.added";
    case "task.removed":
      return "node.removed";
    case "task.status_changed":
      return "node.status_changed";
    case "edge.added":
    case "edge.removed":
    case "edge.status_changed":
    case "annotation.set":
    case "annotation.deleted":
      return eventType;
    default:
      return null;
  }
}

function payloadRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function graphMutationValue(event: SampleRuntimeEventView, mutationType: MutationType): Record<string, unknown> {
  const payload = payloadRecord(event.payload);

  if (event.eventType === "task.added" && mutationType === "node.added") {
    const task = payloadRecord(event.task);
    return {
      task_slug: String(event.taskSlug ?? task.task_slug ?? task.name ?? event.targetId ?? "task"),
      instance_key: String(task.instance_key ?? payload.instance_key ?? event.targetId ?? "task"),
      description: String(task.description ?? payload.description ?? ""),
      status: String(event.status ?? task.status ?? "pending"),
      assigned_worker_slug:
        typeof task.assigned_worker_slug === "string"
          ? task.assigned_worker_slug
          : typeof payload.assigned_worker_slug === "string"
            ? payload.assigned_worker_slug
            : null,
    };
  }

  if (
    (event.eventType === "task.status_changed" && mutationType === "node.status_changed") ||
    (event.eventType === "edge.status_changed" && mutationType === "edge.status_changed")
  ) {
    return { status: event.status };
  }

  if (
    (event.eventType === "edge.added" || event.eventType === "edge.removed") &&
    (mutationType === "edge.added" || mutationType === "edge.removed")
  ) {
    const edge = event.eventType === "edge.added" ? payloadRecord(event.edge) : {};
    return {
      source_task_id: event.sourceTaskId,
      target_task_id: event.targetTaskId,
      status: String(event.eventType === "edge.added" ? (event.status ?? edge.status ?? "pending") : "removed"),
    };
  }

  if (
    (event.eventType === "annotation.set" || event.eventType === "annotation.deleted") &&
    (mutationType === "annotation.set" || mutationType === "annotation.deleted")
  ) {
    return {
      namespace: event.key,
      payload: event.eventType === "annotation.set" ? payloadRecord(event.value) : payload,
    };
  }

  return payload;
}

export function sampleRuntimeEventsToGraphEvents(events: SampleRuntimeEventView[]): SampleGraphEventDto[] {
  return events.flatMap((event, index) => {
    const mutationType = graphMutationType(event.eventType);
    const targetId = event.targetId;
    if (mutationType === null || !targetId) return [];
    const targetType = event.targetType === "edge" ? "edge" : "node";
    const newValue = graphMutationValue(event, mutationType);
    return [
      {
        id: event.eventId,
        sample_id: event.sampleId,
        sequence: index + 1,
        mutation_type: mutationType,
        target_type: targetType,
        target_id: targetId,
        actor: "runtime",
        old_value: null,
        new_value: newValue,
        reason: null,
        created_at: event.timestamp,
      },
    ];
  });
}
