import { z } from "zod"

export const DashboardAgentActionStartedEventSchema = z.object({ "action_id": z.string().uuid(), "action_input": z.string(), "action_type": z.string(), "run_id": z.string().uuid(), "task_id": z.string().uuid(), "timestamp": z.string().datetime({ offset: true }), "worker_id": z.string().uuid(), "worker_name": z.string() }).strict().describe("Emitted when an agent begins a tool call - for dashboard action stream.")
