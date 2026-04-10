import { z } from "zod"

export const DashboardResourcePublishedEventSchema = z.object({ "file_path": z.string(), "mime_type": z.string(), "resource_id": z.string().uuid(), "resource_name": z.string(), "run_id": z.string().uuid(), "size_bytes": z.number().int(), "task_execution_id": z.string().uuid(), "task_id": z.string().uuid(), "timestamp": z.string().datetime({ offset: true }) }).strict().describe("Emitted when a task produces an output resource.")
