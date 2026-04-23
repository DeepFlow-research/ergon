import { z } from "zod"

export const DashboardSandboxCreatedEventSchema = z.object({ "run_id": z.string().uuid(), "task_id": z.string().uuid(), "sandbox_id": z.string(), "template": z.union([z.string(), z.null()]).default(null), "timeout_minutes": z.number().int(), "timestamp": z.string().datetime({ offset: true }) }).catchall(z.any())
