import { SampleWorkspacePage } from "@/components/sample/SampleWorkspacePage";
import { loadRunSnapshot } from "@/lib/server-data/samples";
import type { SerializedSampleWorkspaceState } from "@/lib/types";

interface LegacySamplePageProps {
  params: Promise<{
    sampleId: string;
  }>;
}

export default async function SamplePage({ params }: LegacySamplePageProps) {
  const { sampleId } = await params;
  let initialRunState: SerializedSampleWorkspaceState | null = null;
  let ssrError: string | null = null;

  const result = await loadRunSnapshot(sampleId);
  if (result.ok) {
    initialRunState = result.data;
  } else {
    const detail = (result.body as { detail?: string })?.detail;
    ssrError = detail ?? `Sample API returned ${result.status}`;
  }

  return <SampleWorkspacePage sampleId={sampleId} initialRunState={initialRunState} ssrError={ssrError} />;
}
