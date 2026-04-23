import { z } from "zod"

export const CohortUpdatedEventSchema = z.object({ "cohort_id": z.string().uuid(), "summary": z.record(z.string(), z.any()) }).catchall(z.any()).describe("TODO(E2b): tighten ``summary`` to ``CohortSummaryDto`` and update\nthe emitter accordingly.")
