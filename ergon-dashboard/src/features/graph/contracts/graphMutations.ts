import { z } from "zod";

export const GraphTargetTypeSchema = z.enum(["node", "edge"]);
export type GraphTargetType = z.infer<typeof GraphTargetTypeSchema>;

export const MutationTypeSchema = z.enum([
  "node.added",
  "node.removed",
  "node.status_changed",
  "node.field_changed",
  "edge.added",
  "edge.removed",
  "edge.status_changed",
  "annotation.set",
  "annotation.deleted",
]);
export type MutationType = z.infer<typeof MutationTypeSchema>;

export const UpdatableNodeFieldSchema = z.enum([
  "description",
  "assigned_worker_key",
]);
export type UpdatableNodeField = z.infer<typeof UpdatableNodeFieldSchema>;

export const NodeAddedValueSchema = z.object({
  task_key: z.string().min(1),
  instance_key: z.string().min(1),
  description: z.string(),
  status: z.string(),
  assigned_worker_key: z.string().nullable(),
});
export type NodeAddedValue = z.infer<typeof NodeAddedValueSchema>;

export const NodeStatusChangedValueSchema = z.object({
  status: z.string(),
});
export type NodeStatusChangedValue = z.infer<typeof NodeStatusChangedValueSchema>;

export const NodeFieldChangedValueSchema = z.object({
  field: UpdatableNodeFieldSchema,
  value: z.string().nullable(),
});
export type NodeFieldChangedValue = z.infer<typeof NodeFieldChangedValueSchema>;

export const EdgeAddedValueSchema = z.object({
  source_node_id: z.string().uuid(),
  target_node_id: z.string().uuid(),
  status: z.string(),
});
export type EdgeAddedValue = z.infer<typeof EdgeAddedValueSchema>;

export const EdgeStatusChangedValueSchema = z.object({
  status: z.string(),
});
export type EdgeStatusChangedValue = z.infer<typeof EdgeStatusChangedValueSchema>;

export const AnnotationValueSchema = z.object({
  namespace: z.string(),
  payload: z.record(z.string(), z.unknown()),
});
export type AnnotationValue = z.infer<typeof AnnotationValueSchema>;

export const GraphMutationDtoSchema = z.object({
  id: z.string().uuid(),
  run_id: z.string().uuid(),
  sequence: z.number().int().nonnegative(),
  mutation_type: MutationTypeSchema,
  target_type: GraphTargetTypeSchema,
  target_id: z.string().uuid(),
  actor: z.string().min(1),
  old_value: z.record(z.string(), z.unknown()).nullable(),
  new_value: z.record(z.string(), z.unknown()),
  reason: z.string().nullable(),
  created_at: z.string().datetime({ offset: true }),
});
export type GraphMutationDto = z.infer<typeof GraphMutationDtoSchema>;

export function parseGraphMutationDto(input: unknown): GraphMutationDto {
  return GraphMutationDtoSchema.parse(input);
}

export function parseGraphMutationDtoArray(input: unknown): GraphMutationDto[] {
  return z.array(GraphMutationDtoSchema).parse(input);
}
