import { z } from "zod"

export const DashboardSandboxCommandEventSchema = z.object({ "run_id": z.string().uuid(), "task_id": z.string().uuid(), "sandbox_id": z.string(), "command": z.string(), "stdout": z.union([z.string(), z.null()]).default(null), "stderr": z.union([z.string(), z.null()]).default(null), "exit_code": z.union([z.number().int(), z.null()]).default(null), "duration_ms": z.union([z.number().int(), z.null()]).default(null), "timestamp": z.string().datetime({ offset: true }) }).catchall(z.any())
