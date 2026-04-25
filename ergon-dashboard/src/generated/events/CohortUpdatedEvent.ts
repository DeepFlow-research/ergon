import { z } from "zod"

export const CohortUpdatedEventSchema = z.object({ "cohort_id": z.string().uuid(), "summary": z.any() }).catchall(z.any()).describe("Live cohort summary update.")
