import { z } from "zod"

export const DashboardWorkflowCompletedEventSchema = z.object({ "completed_at": z.string().datetime({ offset: true }), "duration_seconds": z.number(), "error": z.union([z.string(), z.null()]).default(null), "final_score": z.union([z.number(), z.null()]).default(null), "run_id": z.string().uuid(), "status": z.string() }).strict().describe("Emitted when workflow finishes - for dashboard visualization.")
