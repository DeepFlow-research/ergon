import { notFound } from "next/navigation";

import { SampleDetail } from "@/components/samples/SampleDetail";
import { loadSampleState } from "@/lib/server-data/samples";

interface SamplePageProps {
  params: Promise<{
    sampleId: string;
  }>;
}

export default async function SamplePage({ params }: SamplePageProps) {
  const { sampleId } = await params;
  const result = await loadSampleState(sampleId);
  if (!result.ok) {
    if (result.status === 404) notFound();
    throw new Error(`Failed to load sample ${sampleId}: ${result.status}`);
  }

  return <SampleDetail state={result.data} />;
}
