import { RunWorkspacePage } from "@/components/run/RunWorkspacePage";
import { loadCohortDetail } from "@/lib/server-data/cohorts";
import { loadRunSnapshot } from "@/lib/server-data/runs";
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
  let cohortLabel: string | null = null;
  let ssrError: string | null = null;

  const runResult = await loadRunSnapshot(runId);
  if (runResult.ok) {
    initialRunState = runResult.data;
  } else {
    const detail = (runResult.body as { detail?: string })?.detail;
    ssrError = detail ?? `Run API returned ${runResult.status}`;
  }

  const cohortResult = await loadCohortDetail(cohortId);
  if (cohortResult.ok) {
    cohortLabel = cohortResult.data.summary.name;
  }

  return (
    <RunWorkspacePage
      cohortId={cohortId}
      cohortLabel={cohortLabel}
      runId={runId}
      initialRunState={initialRunState}
      ssrError={ssrError}
    />
  );
}
