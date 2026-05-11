"use client";

import { useMemo, useState } from "react";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import { createReplayInitialState, replayToSequence } from "@/features/graph/state/graphMutationReducer";
import type { WorkflowRunState } from "@/lib/types";

export function nearestMutationAtOrBefore(
  mutations: GraphMutationDto[],
  sequence: number,
): GraphMutationDto | null {
  let selected: GraphMutationDto | null = null;
  for (const mutation of mutations) {
    if (mutation.sequence > sequence) break;
    selected = mutation;
  }
  return selected ?? mutations[0] ?? null;
}

export function useRunDisplayState(
  runState: WorkflowRunState | null,
  mutations: GraphMutationDto[],
) {
  // Activities and trace rows are built from full live run state.
  // Inspector and graph may render replay display state.
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [snapshotSequence, setSnapshotSequence] = useState<number | null>(null);
  const currentSequence = snapshotSequence ?? 0;

  const displayState = useMemo(() => {
    if (snapshotSequence === null || mutations.length === 0) return runState;
    if (!runState) return runState;
    const replayBaseState = createReplayInitialState(runState, mutations, snapshotSequence);
    return replayToSequence(mutations, snapshotSequence, replayBaseState);
  }, [runState, mutations, snapshotSequence]);

  const selectedTimelineTime = useMemo(() => {
    if (snapshotSequence === null) return null;
    return nearestMutationAtOrBefore(mutations, snapshotSequence)?.created_at ?? null;
  }, [mutations, snapshotSequence]);

  return {
    displayState,
    selectedActivityId,
    setSelectedActivityId,
    snapshotSequence,
    setSnapshotSequence,
    currentSequence,
    selectedTimelineTime,
  };
}
