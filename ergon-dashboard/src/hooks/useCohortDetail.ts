"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  parseDashboardCohortUpdatedData,
  parseRunCompletedSocketData,
} from "@/lib/contracts/events";
import { parseCohortDetail } from "@/lib/contracts/rest";
import { CohortDetail } from "@/lib/types";
import { useSocket } from "@/hooks/useSocket";

interface UseCohortDetailResult {
  detail: CohortDetail | null;
  isLoading: boolean;
  error: string | null;
}

export function useCohortDetail(
  cohortId: string,
  initialDetail: CohortDetail | null = null,
): UseCohortDetailResult {
  const { socket, isConnected } = useSocket();
  const [detail, setDetail] = useState<CohortDetail | null>(initialDetail);
  const [isLoading, setIsLoading] = useState(initialDetail === null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!cohortId) {
      setDetail(null);
      setIsLoading(false);
      setError(null);
      return;
    }
    try {
      if (initialDetail === null) {
        setIsLoading(true);
      }
      const response = await fetch(`/api/cohorts/${cohortId}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to load cohort (${response.status})`);
      }
      const data = parseCohortDetail(await response.json());
      setDetail(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cohort");
    } finally {
      setIsLoading(false);
    }
  }, [cohortId, initialDetail]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!socket) return;

    const handleCohortUpdated = (payload: unknown) => {
      const data = parseDashboardCohortUpdatedData(payload);
      if (data.cohort_id !== cohortId) return;
      void load();
    };

    const handleRunCompleted = (payload: unknown) => {
      parseRunCompletedSocketData(payload);
      void load();
    };

    socket.on("cohort:updated", handleCohortUpdated);
    socket.on("run:completed", handleRunCompleted);
    return () => {
      socket.off("cohort:updated", handleCohortUpdated);
      socket.off("run:completed", handleRunCompleted);
    };
  }, [socket, cohortId, load]);

  useEffect(() => {
    if (!isConnected && socket) {
      setError("Disconnected from server");
    }
  }, [isConnected, socket]);

  return useMemo(
    () => ({
      detail,
      isLoading,
      error,
    }),
    [detail, error, isLoading],
  );
}
