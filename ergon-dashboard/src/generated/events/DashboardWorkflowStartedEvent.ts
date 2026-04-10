import { z } from "zod"

export const DashboardWorkflowStartedEventSchema = z.object({ "experiment_id": z.string().uuid(), "run_id": z.string().uuid(), "started_at": z.string().datetime({ offset: true }), "task_tree": z.any(), "total_leaf_tasks": z.number().int(), "total_tasks": z.number().int(), "workflow_name": z.string() }).strict().describe("Emitted when execute_task() is called - for dashboard visualization.")
