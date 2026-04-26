import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { config } from "@/lib/config";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRun } from "@/lib/testing/dashboardHarness";
import type { SerializedWorkflowRunState } from "@/lib/types";

interface LegacyRunPageProps {
  params: Promise<{
    runId: string;
  }>;
}

export default async function RunPage({ params }: LegacyRunPageProps) {
  const { runId } = await params;
  let initialRunState: SerializedWorkflowRunState | null = null;
  let ssrError: string | null = null;

  if (config.enableTestHarness) {
    initialRunState = getHarnessRun(runId);
  } else {
    try {
      const response = await fetchErgonApi(`/runs/${runId}`);
      if (response.ok) {
        initialRunState = parseRunSnapshot(await response.json());
      } else {
        ssrError = `Run API returned ${response.status}`;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[RunPage] SSR fetch failed for run ${runId}:`, msg);
      ssrError = msg.includes("Cannot find module")
        ? "Stale build — the .next cache is corrupted. Restart the dev server."
        : `Server-side data fetch failed: ${msg}`;
      initialRunState = null;
    }
  }

  return <RunWorkspacePage runId={runId} initialRunState={initialRunState} ssrError={ssrError} />;
}
