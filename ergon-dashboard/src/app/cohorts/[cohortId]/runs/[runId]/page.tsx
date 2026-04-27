import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { config } from "@/lib/config";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRun } from "@/lib/testing/dashboardHarness";
import type { SerializedWorkflowRunState } from "@/lib/types";

interface CohortRunPageProps {
  params: Promise<{
    cohortId: string;
    runId: string;
  }>;
}

export default async function CohortRunPage({ params }: CohortRunPageProps) {
  const { cohortId, runId } = await params;
  let initialRunState: SerializedWorkflowRunState | null = null;
  let ssrError: string | null = null;

  if (config.enableTestHarness) {
    initialRunState = getHarnessRun(runId);
  } else {
    try {
      const runResponse = await fetchErgonApi(`/runs/${runId}`);
      if (runResponse.ok) {
        initialRunState = parseRunSnapshot(await runResponse.json());
      } else {
        ssrError = `Run API returned ${runResponse.status}`;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[CohortRunPage] SSR fetch failed for run ${runId}:`, msg);
      ssrError = msg.includes("Cannot find module")
        ? "Stale build — the .next cache is corrupted. Restart the dev server (rm -rf .next && docker compose restart dashboard)."
        : `Server-side data fetch failed: ${msg}`;
      initialRunState = null;
    }
  }

  return (
    <RunWorkspacePage
      cohortId={cohortId}
      runId={runId}
      initialRunState={initialRunState}
      ssrError={ssrError}
    />
  );
}
