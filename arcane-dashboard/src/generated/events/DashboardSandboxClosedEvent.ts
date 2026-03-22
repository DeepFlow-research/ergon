import { z } from "zod"

export const DashboardSandboxClosedEventSchema = z.object({ "reason": z.string(), "sandbox_id": z.string(), "task_id": z.string().uuid(), "timestamp": z.string().datetime({ offset: true }) }).strict().describe("Emitted when a sandbox is terminated.")
