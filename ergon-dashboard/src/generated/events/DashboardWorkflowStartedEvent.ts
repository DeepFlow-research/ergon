import { z } from "zod"

export const DashboardWorkflowStartedEventSchema = z.object({ "run_id": z.string().uuid(), "experiment_id": z.string().uuid(), "workflow_name": z.string(), "task_tree": z.any(), "started_at": z.string().datetime({ offset: true }), "total_tasks": z.number().int(), "total_leaf_tasks": z.number().int() }).catchall(z.any())
