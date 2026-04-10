import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { config } from "@/lib/config";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchArcaneApi } from "@/lib/serverApi";
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

  if (config.enableTestHarness) {
    initialRunState = getHarnessRun(runId);
  } else {
    try {
      const response = await fetchArcaneApi(`/runs/${runId}`);
      if (response.ok) {
        initialRunState = parseRunSnapshot(await response.json());
      }
    } catch {
      initialRunState = null;
    }
  }

  return <RunWorkspacePage runId={runId} initialRunState={initialRunState} />;
}
