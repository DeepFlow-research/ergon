"use client";

import { useCallback, useEffect, useState } from "react";

import { parseDashboardCohortUpdatedData } from "@/lib/contracts/events";
import { parseCohortSummary, parseCohortSummaryList } from "@/lib/contracts/rest";
import { CohortSummary } from "@/lib/types";
import { useSocket } from "@/hooks/useSocket";

interface UseCohortsResult {
  cohorts: CohortSummary[];
  isLoading: boolean;
  error: string | null;
  updatingCohortIds: string[];
  updateCohortStatus: (cohortId: string, status: CohortSummary["status"]) => Promise<void>;
}

export function useCohorts(): UseCohortsResult {
  const { socket, isConnected } = useSocket();
  const [cohorts, setCohorts] = useState<CohortSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingCohortIds, setUpdatingCohortIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await fetch("/api/cohorts?includeArchived=true", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to load cohorts (${response.status})`);
      }
      const data = parseCohortSummaryList(await response.json());
      setCohorts(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cohorts");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateCohortStatus = useCallback(
    async (cohortId: string, status: CohortSummary["status"]) => {
      let previousCohorts: CohortSummary[] = [];

      setUpdatingCohortIds((prev) => [...prev, cohortId]);
      setCohorts((prev) => {
        previousCohorts = prev;
        return prev.map((cohort) => (cohort.cohort_id === cohortId ? { ...cohort, status } : cohort));
      });

      try {
        const response = await fetch(`/api/cohorts/${cohortId}`, {
          method: "PATCH",
          headers: {
            "content-type": "application/json",
          },
          body: JSON.stringify({ status }),
        });

        if (!response.ok) {
          throw new Error(`Failed to update cohort (${response.status})`);
        }

        const updated = parseCohortSummary(await response.json());
        setCohorts((prev) =>
          prev.map((cohort) => (cohort.cohort_id === cohortId ? updated : cohort)),
        );
        setError(null);
      } catch (err) {
        setCohorts(previousCohorts);
        setError(err instanceof Error ? err.message : "Failed to update cohort");
        throw err;
      } finally {
        setUpdatingCohortIds((prev) => prev.filter((id) => id !== cohortId));
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!socket) return;

    const handleCohortUpdated = (payload: unknown) => {
      const data = parseDashboardCohortUpdatedData(payload);
      setCohorts((prev) => {
        const existing = prev.some((cohort) => cohort.cohort_id === data.cohort_id);
        if (!existing) {
          return [data.summary, ...prev];
        }
        return prev.map((cohort) =>
          cohort.cohort_id === data.cohort_id ? data.summary : cohort,
        );
      });
    };

    socket.on("cohort:updated", handleCohortUpdated);
    return () => {
      socket.off("cohort:updated", handleCohortUpdated);
    };
  }, [socket]);

  useEffect(() => {
    if (!isConnected && socket) {
      setError("Disconnected from server");
    }
  }, [isConnected, socket]);

  return {
    cohorts,
    isLoading,
    error,
    updatingCohortIds,
    updateCohortStatus,
  };
}
