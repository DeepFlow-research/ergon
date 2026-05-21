import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";

export type ReplayDirection = "previous" | "next";

export function resolveReplayStep(
  mutations: GraphMutationDto[],
  currentSequence: number | null,
  direction: ReplayDirection,
): number | null {
  if (mutations.length === 0) return null;
  const sequences = [...new Set(mutations.map((mutation) => mutation.sequence))].sort(
    (a, b) => a - b,
  );
  if (sequences.length === 0) return null;
  if (currentSequence === null) {
    return direction === "next" ? sequences[0] : sequences[sequences.length - 1];
  }

  if (direction === "next") {
    return sequences.find((sequence) => sequence > currentSequence) ?? currentSequence;
  }

  return sequences.findLast((sequence) => sequence < currentSequence) ?? currentSequence;
}
