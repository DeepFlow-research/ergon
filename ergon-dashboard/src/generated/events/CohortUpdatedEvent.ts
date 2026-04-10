import { z } from "zod"

export const CohortUpdatedEventSchema = z.object({ "cohort_id": z.string().uuid(), "summary": z.any() }).strict().describe("Frontend-facing event emitted whenever cohort aggregate state changes.")
