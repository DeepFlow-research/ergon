import { z } from "zod"

export const DashboardThreadMessageCreatedEventSchema = z.object({ "sample_id": z.string().uuid(), "thread": z.any(), "message": z.any() }).catchall(z.any()).describe("Embeds full RunCommunicationThreadDto + RunCommunicationMessageDto.")
