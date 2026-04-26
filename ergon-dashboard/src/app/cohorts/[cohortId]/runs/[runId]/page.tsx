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
  let ssrError: string | null = null;

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
      } else {
        ssrError = `Run API returned ${runResponse.status}`;
      }
      if (cohortResponse.ok) {
        initialCohortDetail = parseCohortDetail(await cohortResponse.json());
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[CohortRunPage] SSR fetch failed for run ${runId}:`, msg);
      ssrError = msg.includes("Cannot find module")
        ? "Stale build — the .next cache is corrupted. Restart the dev server (rm -rf .next && docker compose restart dashboard)."
        : `Server-side data fetch failed: ${msg}`;
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
      ssrError={ssrError}
    />
  );
}
