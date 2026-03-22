import { z } from "zod";
import { CohortUpdatedEventSchema } from "./CohortUpdatedEvent";
import { DashboardWorkflowStartedEventSchema } from "./DashboardWorkflowStartedEvent";
import { DashboardWorkflowCompletedEventSchema } from "./DashboardWorkflowCompletedEvent";
import { DashboardTaskStatusChangedEventSchema } from "./DashboardTaskStatusChangedEvent";
import { DashboardAgentActionStartedEventSchema } from "./DashboardAgentActionStartedEvent";
import { DashboardAgentActionCompletedEventSchema } from "./DashboardAgentActionCompletedEvent";
import { DashboardResourcePublishedEventSchema } from "./DashboardResourcePublishedEvent";
import { DashboardSandboxCreatedEventSchema } from "./DashboardSandboxCreatedEvent";
import { DashboardSandboxCommandEventSchema } from "./DashboardSandboxCommandEvent";
import { DashboardSandboxClosedEventSchema } from "./DashboardSandboxClosedEvent";
import { DashboardThreadMessageCreatedEventSchema } from "./DashboardThreadMessageCreatedEvent";
import { DashboardTaskEvaluationUpdatedEventSchema } from "./DashboardTaskEvaluationUpdatedEvent";

export { CohortUpdatedEventSchema };
export type CohortUpdatedEvent = z.infer<typeof CohortUpdatedEventSchema>;
export { DashboardWorkflowStartedEventSchema };
export type DashboardWorkflowStartedEvent = z.infer<typeof DashboardWorkflowStartedEventSchema>;
export { DashboardWorkflowCompletedEventSchema };
export type DashboardWorkflowCompletedEvent = z.infer<typeof DashboardWorkflowCompletedEventSchema>;
export { DashboardTaskStatusChangedEventSchema };
export type DashboardTaskStatusChangedEvent = z.infer<typeof DashboardTaskStatusChangedEventSchema>;
export { DashboardAgentActionStartedEventSchema };
export type DashboardAgentActionStartedEvent = z.infer<typeof DashboardAgentActionStartedEventSchema>;
export { DashboardAgentActionCompletedEventSchema };
export type DashboardAgentActionCompletedEvent = z.infer<typeof DashboardAgentActionCompletedEventSchema>;
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

export const dashboardEventSchemas = {
  "dashboard/cohort.updated": CohortUpdatedEventSchema,
  "dashboard/workflow.started": DashboardWorkflowStartedEventSchema,
  "dashboard/workflow.completed": DashboardWorkflowCompletedEventSchema,
  "dashboard/task.status_changed": DashboardTaskStatusChangedEventSchema,
  "dashboard/agent.action_started": DashboardAgentActionStartedEventSchema,
  "dashboard/agent.action_completed": DashboardAgentActionCompletedEventSchema,
  "dashboard/resource.published": DashboardResourcePublishedEventSchema,
  "dashboard/sandbox.created": DashboardSandboxCreatedEventSchema,
  "dashboard/sandbox.command": DashboardSandboxCommandEventSchema,
  "dashboard/sandbox.closed": DashboardSandboxClosedEventSchema,
  "dashboard/thread.message_created": DashboardThreadMessageCreatedEventSchema,
  "dashboard/task.evaluation_updated": DashboardTaskEvaluationUpdatedEventSchema,
} as const;

export type DashboardEventName = keyof typeof dashboardEventSchemas;

