import { z } from "zod";
import { SampleRuntimeEventViewSchema } from "@/lib/contracts/rest";

export const DashboardSampleRuntimeEventSchema = z.object({
  event: SampleRuntimeEventViewSchema,
}).catchall(z.any());
