import { z } from "zod"

export const DashboardSandboxCommandEventSchema = z.object({ "command": z.string(), "duration_ms": z.union([z.number().int(), z.null()]).default(null), "exit_code": z.union([z.number().int(), z.null()]).default(null), "sandbox_id": z.string(), "stderr": z.union([z.string(), z.null()]).default(null), "stdout": z.union([z.string(), z.null()]).default(null), "task_id": z.string().uuid(), "timestamp": z.string().datetime({ offset: true }) }).strict().describe("Emitted when a command is executed in a sandbox.")
