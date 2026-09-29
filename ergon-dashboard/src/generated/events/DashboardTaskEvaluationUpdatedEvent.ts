import { z } from "zod"

export const DashboardTaskEvaluationUpdatedEventSchema = z.object({ "sample_id": z.string().uuid(), "task_id": z.string().uuid() }).catchall(z.any()).describe("Invalidates the task's evaluation; the dashboard reads the persisted result.")
