import { notFound } from "next/navigation";

import { SampleWorkspacePage } from "@/components/sample/SampleWorkspacePage";
import { loadSampleSnapshot } from "@/lib/server-data/samples";

interface SamplePageProps {
  params: Promise<{
    sampleId: string;
  }>;
}

export default async function SamplePage({ params }: SamplePageProps) {
  const { sampleId } = await params;
  const result = await loadSampleSnapshot(sampleId);
  if (!result.ok) {
    if (result.status === 404) notFound();
    return <SampleWorkspacePage sampleId={sampleId} ssrError={`API returned ${result.status}`} />;
  }

  return <SampleWorkspacePage sampleId={sampleId} initialRunState={result.data} />;
}
