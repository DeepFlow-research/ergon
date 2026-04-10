import { z } from "zod"

export const DashboardTaskEvaluationUpdatedEventSchema = z.object({ "evaluation": z.any(), "run_id": z.string().uuid(), "task_id": z.union([z.string().uuid(), z.null()]).default(null) }).strict().describe("Emitted when task evaluation truth becomes available or changes.")
