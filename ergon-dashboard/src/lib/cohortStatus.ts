import { CohortSummary, ExperimentCohortStatus, RunLifecycleStatus } from "@/lib/types";

type CohortDisplayStatus = ExperimentCohortStatus | RunLifecycleStatus;

export function getCohortDisplayStatus(
  cohort: Pick<CohortSummary, "status" | "total_runs" | "status_counts">,
): CohortDisplayStatus {
  if (cohort.status === "archived") {
    return "archived";
  }

  if (cohort.total_runs === 0) {
    return "active";
  }

  if (cohort.status_counts.executing > 0) {
    return "executing";
  }

  if (cohort.status_counts.evaluating > 0) {
    return "evaluating";
  }

  if (cohort.status_counts.pending > 0) {
    return "pending";
  }

  if (cohort.status_counts.failed > 0) {
    return "failed";
  }

  return "completed";
}
