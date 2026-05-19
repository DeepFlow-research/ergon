import { z } from "zod";
import { GraphMutationDtoSchema } from "@/features/graph/contracts/graphMutations";

export const DashboardGraphMutationEventSchema = z.object({
  mutation: GraphMutationDtoSchema,
}).catchall(z.any());
