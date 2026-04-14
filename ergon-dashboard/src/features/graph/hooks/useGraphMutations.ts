import { useRef, useCallback } from "react";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type { WorkflowRunState } from "@/lib/types";
import { applyGraphMutation } from "@/features/graph/state/graphMutationReducer";

const DEBOUNCE_MS = 200;

export function useGraphMutations(
  setRunState: React.Dispatch<React.SetStateAction<WorkflowRunState | null>>,
) {
  const buffer = useRef<DashboardGraphMutationData[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(() => {
    const mutations = buffer.current;
    buffer.current = [];
    if (mutations.length === 0) return;
    setRunState((prev) => {
      if (!prev) return prev;
      return mutations.reduce(applyGraphMutation, {
        ...prev,
        tasks: new Map(prev.tasks),
      });
    });
  }, [setRunState]);

  const handleGraphMutation = useCallback(
    (mutation: DashboardGraphMutationData) => {
      buffer.current.push(mutation);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(flush, DEBOUNCE_MS);
    },
    [flush],
  );

  return { handleGraphMutation };
}
