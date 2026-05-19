import { z } from "zod";
import { DashboardWorkflowStartedEventSchema } from "./DashboardWorkflowStartedEvent";
import { DashboardWorkflowCompletedEventSchema } from "./DashboardWorkflowCompletedEvent";
import { DashboardTaskStatusChangedEventSchema } from "./DashboardTaskStatusChangedEvent";
import { DashboardResourcePublishedEventSchema } from "./DashboardResourcePublishedEvent";
import { DashboardSandboxCreatedEventSchema } from "./DashboardSandboxCreatedEvent";
import { DashboardSandboxCommandEventSchema } from "./DashboardSandboxCommandEvent";
import { DashboardSandboxClosedEventSchema } from "./DashboardSandboxClosedEvent";
import { DashboardThreadMessageCreatedEventSchema } from "./DashboardThreadMessageCreatedEvent";
import { DashboardTaskEvaluationUpdatedEventSchema } from "./DashboardTaskEvaluationUpdatedEvent";
import { DashboardGraphMutationEventSchema } from "./DashboardGraphMutationEvent";
import { DashboardContextEventEventSchema } from "./DashboardContextEventEvent";

export { DashboardWorkflowStartedEventSchema };
export type DashboardWorkflowStartedEvent = z.infer<typeof DashboardWorkflowStartedEventSchema>;
export { DashboardWorkflowCompletedEventSchema };
export type DashboardWorkflowCompletedEvent = z.infer<typeof DashboardWorkflowCompletedEventSchema>;
export { DashboardTaskStatusChangedEventSchema };
export type DashboardTaskStatusChangedEvent = z.infer<typeof DashboardTaskStatusChangedEventSchema>;
export { DashboardResourcePublishedEventSchema };
export type DashboardResourcePublishedEvent = z.infer<typeof DashboardResourcePublishedEventSchema>;
export { DashboardSandboxCreatedEventSchema };
export type DashboardSandboxCreatedEvent = z.infer<typeof DashboardSandboxCreatedEventSchema>;
export { DashboardSandboxCommandEventSchema };
export type DashboardSandboxCommandEvent = z.infer<typeof DashboardSandboxCommandEventSchema>;
export { DashboardSandboxClosedEventSchema };
export type DashboardSandboxClosedEvent = z.infer<typeof DashboardSandboxClosedEventSchema>;
export { DashboardThreadMessageCreatedEventSchema };
export type DashboardThreadMessageCreatedEvent = z.infer<typeof DashboardThreadMessageCreatedEventSchema>;
export { DashboardTaskEvaluationUpdatedEventSchema };
export type DashboardTaskEvaluationUpdatedEvent = z.infer<typeof DashboardTaskEvaluationUpdatedEventSchema>;
export { DashboardGraphMutationEventSchema };
export type DashboardGraphMutationEvent = z.infer<typeof DashboardGraphMutationEventSchema>;
export { DashboardContextEventEventSchema };
export type DashboardContextEventEvent = z.infer<typeof DashboardContextEventEventSchema>;

export const dashboardEventSchemas = {
  "dashboard/workflow.started": DashboardWorkflowStartedEventSchema,
  "dashboard/workflow.completed": DashboardWorkflowCompletedEventSchema,
  "dashboard/task.status_changed": DashboardTaskStatusChangedEventSchema,
  "dashboard/resource.published": DashboardResourcePublishedEventSchema,
  "dashboard/sandbox.created": DashboardSandboxCreatedEventSchema,
  "dashboard/sandbox.command": DashboardSandboxCommandEventSchema,
  "dashboard/sandbox.closed": DashboardSandboxClosedEventSchema,
  "dashboard/thread.message_created": DashboardThreadMessageCreatedEventSchema,
  "dashboard/task.evaluation_updated": DashboardTaskEvaluationUpdatedEventSchema,
  "dashboard/graph.mutation": DashboardGraphMutationEventSchema,
  "dashboard/context.event": DashboardContextEventEventSchema,
} as const;

export type DashboardEventName = keyof typeof dashboardEventSchemas;

