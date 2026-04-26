import { z } from "zod"

export const DashboardTaskEvaluationUpdatedEventSchema = z.object({ "run_id": z.string().uuid(), "task_id": z.string().uuid(), "evaluation": z.any() }).catchall(z.any()).describe("Embeds the full RunTaskEvaluationDto as ``evaluation``.")
