"use client";

/**
 * useRuns - Hook for managing the list of all workflow runs.
 *
 * Maintains a list of active and recent runs, listening for
 * run:started and run:completed events via Socket.io.
 * 
 * On initial connection, requests all existing runs from the server.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSocket } from "@/hooks/useSocket";

export interface RunSummary {
  id: string;
  name: string;
  status: "running" | "completed" | "failed";
  startedAt: string;
  completedAt: string | null;
  durationSeconds: number | null;
  finalScore: number | null;
  error: string | null;
}

interface UseRunsResult {
  runs: RunSummary[];
  activeRuns: RunSummary[];
  completedRuns: RunSummary[];
  isLoading: boolean;
  error: string | null;
}

export function useRuns(): UseRunsResult {
  const { socket, isConnected } = useSocket();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasRequestedRuns = useRef(false);

  // Handle sync of all runs from server
  const handleSyncRuns = useCallback(
    (syncedRuns: Array<{
      runId: string;
      name: string;
      status: "running" | "completed" | "failed";
      startedAt: string;
      completedAt: string | null;
      durationSeconds: number | null;
      finalScore: number | null;
      error: string | null;
    }>) => {
      console.log("[useRuns] Received sync:runs with", syncedRuns.length, "runs");
      setRuns(syncedRuns.map(r => ({
        id: r.runId,
        name: r.name,
        status: r.status,
        startedAt: r.startedAt,
        completedAt: r.completedAt,
        durationSeconds: r.durationSeconds,
        finalScore: r.finalScore,
        error: r.error,
      })));
      setIsLoading(false);
    },
    []
  );

  // Handle new run started
  const handleRunStarted = useCallback(
    (data: { runId: string; name: string }) => {
      console.log("[useRuns] Received run:started", data);
      setRuns((prev) => {
        // Check if run already exists
        if (prev.some((r) => r.id === data.runId)) {
          return prev;
        }

        const newRun: RunSummary = {
          id: data.runId,
          name: data.name,
          status: "running",
          startedAt: new Date().toISOString(),
          completedAt: null,
          durationSeconds: null,
          finalScore: null,
          error: null,
        };

        return [newRun, ...prev];
      });
    },
    []
  );

  // Handle run completed
  const handleRunCompleted = useCallback(
    (data: {
      runId: string;
      status: "completed" | "failed";
      durationSeconds: number;
      finalScore: number | null;
      error: string | null;
    }) => {
      console.log("[useRuns] Received run:completed", data);
      setRuns((prev) =>
        prev.map((run) => {
          if (run.id !== data.runId) return run;

          return {
            ...run,
            status: data.status,
            completedAt: new Date().toISOString(),
            durationSeconds: data.durationSeconds,
            finalScore: data.finalScore,
            error: data.error,
          };
        })
      );
    },
    []
  );

  // Set up socket listeners
  useEffect(() => {
    if (!socket) return;

    socket.on("sync:runs", handleSyncRuns);
    socket.on("run:started", handleRunStarted);
    socket.on("run:completed", handleRunCompleted);

    return () => {
      socket.off("sync:runs", handleSyncRuns);
      socket.off("run:started", handleRunStarted);
      socket.off("run:completed", handleRunCompleted);
    };
  }, [socket, handleSyncRuns, handleRunStarted, handleRunCompleted]);

  // Request runs when connected (only once)
  useEffect(() => {
    if (isConnected && socket && !hasRequestedRuns.current) {
      console.log("[useRuns] Connected - requesting runs from server");
      hasRequestedRuns.current = true;
      socket.emit("request:runs");
    }
    
    if (!isConnected) {
      hasRequestedRuns.current = false;
    }
  }, [isConnected, socket]);

  // Update loading/error state based on connection
  useEffect(() => {
    if (isConnected) {
      setError(null);
    } else if (!isConnected && socket) {
      // Socket exists but disconnected - could be reconnecting
      setError("Disconnected from server");
    }
  }, [isConnected, socket]);

  // Derived state
  const activeRuns = useMemo(
    () => runs.filter((r) => r.status === "running"),
    [runs]
  );

  const completedRuns = useMemo(
    () =>
      runs
        .filter((r) => r.status !== "running")
        .sort((a, b) => {
          // Sort by completion time, most recent first
          const aTime = a.completedAt || a.startedAt;
          const bTime = b.completedAt || b.startedAt;
          return bTime.localeCompare(aTime);
        }),
    [runs]
  );

  return {
    runs,
    activeRuns,
    completedRuns,
    isLoading,
    error,
  };
}
