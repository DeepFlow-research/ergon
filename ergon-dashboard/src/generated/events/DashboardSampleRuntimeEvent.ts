import { z } from "zod"

export const DashboardSampleRuntimeEventSchema = z.object({ "event": z.any() }).catchall(z.any())
