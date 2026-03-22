import { z } from "zod"

export const DashboardThreadMessageCreatedEventSchema = z.object({ "message": z.any(), "run_id": z.string().uuid(), "thread": z.any() }).strict().describe("Emitted when a thread gains a new message.")
