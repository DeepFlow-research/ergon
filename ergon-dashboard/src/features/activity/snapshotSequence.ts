import type { SampleGraphEventDto } from "@/features/graph/contracts/graphMutations";
import type { SampleActivity } from "./types";

export function resolveActivitySnapshotSequence(
  activity: SampleActivity,
  mutations: SampleGraphEventDto[],
): number | null {
  if (activity.sequence !== null) return activity.sequence;

  const activityMs = Date.parse(activity.startAt);
  if (!Number.isFinite(activityMs)) return null;

  let selected: SampleGraphEventDto | null = null;
  let selectedMs = Number.NEGATIVE_INFINITY;
  for (const mutation of mutations) {
    const mutationMs = Date.parse(mutation.created_at);
    if (!Number.isFinite(mutationMs)) continue;
    if (mutationMs > activityMs) continue;
    if (
      mutationMs > selectedMs ||
      (mutationMs === selectedMs && (!selected || mutation.sequence > selected.sequence))
    ) {
      selected = mutation;
      selectedMs = mutationMs;
    }
  }
  return selected?.sequence ?? null;
}
