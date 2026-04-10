import { z } from "zod"

export const DashboardSandboxCreatedEventSchema = z.object({ "run_id": z.string().uuid(), "sandbox_id": z.string(), "task_id": z.string().uuid(), "template": z.union([z.string(), z.null()]).default(null), "timeout_minutes": z.number().int(), "timestamp": z.string().datetime({ offset: true }) }).strict().describe("Emitted when an E2B sandbox is created for a task.")
