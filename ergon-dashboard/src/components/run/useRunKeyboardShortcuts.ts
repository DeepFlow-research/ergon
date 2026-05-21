"use client";

import { useEffect } from "react";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import { TaskStatus } from "@/lib/types";
import { resolveReplayStep } from "./replayNavigation";

export function useRunKeyboardShortcuts(options: {
  selectedTaskId: string | null;
  clearSelectedTask: () => void;
  snapshotSequence: number | null;
  setSnapshotSequence: (sequence: number | null) => void;
  statusFilter: TaskStatus | null;
  setStatusFilter: (status: TaskStatus | null | ((previous: TaskStatus | null) => TaskStatus | null)) => void;
  toggleEventStream: () => void;
  mutations: GraphMutationDto[];
}) {
  useEffect(() => {
    const statusOrder: TaskStatus[] = [
      TaskStatus.PENDING,
      TaskStatus.READY,
      TaskStatus.RUNNING,
      TaskStatus.COMPLETED,
      TaskStatus.FAILED,
      TaskStatus.CANCELLED,
    ];

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) {
          return;
        }
      }

      if (e.key === "Escape") {
        if (options.selectedTaskId) {
          options.clearSelectedTask();
          return;
        }
        if (options.snapshotSequence !== null) {
          options.setSnapshotSequence(null);
          return;
        }
        if (options.statusFilter) {
          options.setStatusFilter(null);
        }
        return;
      }

      if (e.key === "e" || e.key === "E") {
        options.toggleEventStream();
        return;
      }

      if (e.key === "ArrowLeft") {
        const sequence = resolveReplayStep(options.mutations, options.snapshotSequence, "previous");
        if (sequence !== null) options.setSnapshotSequence(sequence);
        return;
      }
      if (e.key === "ArrowRight") {
        const sequence = resolveReplayStep(options.mutations, options.snapshotSequence, "next");
        if (sequence !== null) options.setSnapshotSequence(sequence);
        return;
      }

      if ((e.key === "d" || e.key === "D") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (options.selectedTaskId) options.clearSelectedTask();
        return;
      }

      const idx = Number(e.key) - 1;
      if (!Number.isNaN(idx) && idx >= 0 && idx < statusOrder.length) {
        const next = statusOrder[idx];
        options.setStatusFilter((prev) => (prev === next ? null : next));
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [options]);
}
