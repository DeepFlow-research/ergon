import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { loadRunSnapshot } from "@/lib/server-data/runs";
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

  const result = await loadRunSnapshot(runId);
  if (result.ok) {
    initialRunState = result.data;
  } else {
    const detail = (result.body as { detail?: string })?.detail;
    ssrError = detail ?? `Run API returned ${result.status}`;
  }

  return <RunWorkspacePage runId={runId} initialRunState={initialRunState} ssrError={ssrError} />;
}
