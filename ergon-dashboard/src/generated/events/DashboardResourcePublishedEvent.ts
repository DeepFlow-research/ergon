import { z } from "zod"

export const DashboardResourcePublishedEventSchema = z.object({ "run_id": z.string().uuid(), "task_id": z.string().uuid(), "task_execution_id": z.string().uuid(), "resource_id": z.string().uuid(), "resource_name": z.string(), "mime_type": z.string(), "size_bytes": z.number().int(), "file_path": z.string(), "timestamp": z.string().datetime({ offset: true }) }).catchall(z.any())
