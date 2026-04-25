import { z } from "zod"

export const DashboardWorkflowCompletedEventSchema = z.object({ "run_id": z.string().uuid(), "status": z.string(), "completed_at": z.string().datetime({ offset: true }), "duration_seconds": z.number(), "final_score": z.union([z.number(), z.null()]).default(null), "error": z.union([z.string(), z.null()]).default(null) }).catchall(z.any())
