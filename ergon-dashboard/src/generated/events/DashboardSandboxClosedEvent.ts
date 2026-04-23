import { z } from "zod"

export const DashboardSandboxClosedEventSchema = z.object({ "task_id": z.string().uuid(), "sandbox_id": z.string(), "reason": z.string(), "timestamp": z.string().datetime({ offset: true }) }).catchall(z.any())
