import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { config } from "@/lib/config";
import { parseCohortDetail, parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessCohort, getHarnessRun } from "@/lib/testing/dashboardHarness";
import type { CohortDetail, SerializedWorkflowRunState } from "@/lib/types";

interface CohortRunPageProps {
  params: Promise<{
    cohortId: string;
    runId: string;
  }>;
}

export default async function CohortRunPage({ params }: CohortRunPageProps) {
  const { cohortId, runId } = await params;
  let initialRunState: SerializedWorkflowRunState | null = null;
  let initialCohortDetail: CohortDetail | null = null;

  if (config.enableTestHarness) {
    initialRunState = getHarnessRun(runId);
    initialCohortDetail = getHarnessCohort(cohortId);
  } else {
    try {
      const [runResponse, cohortResponse] = await Promise.all([
        fetchErgonApi(`/runs/${runId}`),
        fetchErgonApi(`/cohorts/${cohortId}`),
      ]);
      if (runResponse.ok) {
        initialRunState = parseRunSnapshot(await runResponse.json());
      }
      if (cohortResponse.ok) {
        initialCohortDetail = parseCohortDetail(await cohortResponse.json());
      }
    } catch {
      initialRunState = null;
      initialCohortDetail = null;
    }
  }

  return (
    <RunWorkspacePage
      cohortId={cohortId}
      runId={runId}
      initialRunState={initialRunState}
      initialCohortDetail={initialCohortDetail}
    />
  );
}
