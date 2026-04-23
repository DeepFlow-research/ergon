import { z } from "zod"

export const DashboardThreadMessageCreatedEventSchema = z.object({ "run_id": z.string().uuid(), "thread": z.record(z.string(), z.any()), "message": z.record(z.string(), z.any()) }).catchall(z.any()).describe("Embeds full RunCommunicationThreadDto + RunCommunicationMessageDto (camelCase).\n\nTODO(E2b): tighten ``thread`` / ``message`` to\n``RunCommunicationThreadDto`` / ``RunCommunicationMessageDto``.\nDeferred for the same reason as evaluation above — the emitter\nneeds an updated construction path.")
