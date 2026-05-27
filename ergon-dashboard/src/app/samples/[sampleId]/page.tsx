import { SampleWorkspacePage } from "@/components/sample/SampleWorkspacePage";
import { loadSampleSnapshot } from "@/lib/server-data/samples";
import type { SerializedSampleWorkspaceState } from "@/lib/types";

interface LegacyRunPageProps {
  params: Promise<{
    sampleId: string;
  }>;
}

export default async function RunPage({ params }: LegacyRunPageProps) {
  const { sampleId } = await params;
  let initialRunState: SerializedSampleWorkspaceState | null = null;
  let ssrError: string | null = null;

  const result = await loadSampleSnapshot(sampleId);
  if (result.ok) {
    initialRunState = result.data;
  } else {
    const detail = (result.body as { detail?: string })?.detail;
    ssrError = detail ?? `Run API returned ${result.status}`;
  }

  return <SampleWorkspacePage sampleId={sampleId} initialRunState={initialRunState} ssrError={ssrError} />;
}
