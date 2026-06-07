import { notFound } from "next/navigation";

import { ExperimentDetail } from "@/components/experiments/ExperimentDetail";
import { loadExperimentDetail } from "@/lib/server-data/experiments";

interface ExperimentPageProps {
  params: Promise<{ experimentId: string }>;
}

export default async function ExperimentPage({ params }: ExperimentPageProps) {
  const { experimentId } = await params;
  const result = await loadExperimentDetail(experimentId);
  if (!result.ok) {
    if (result.status === 404) notFound();
    throw new Error(`Failed to load experiment ${experimentId}: ${result.status}`);
  }
  return <ExperimentDetail state={result.data} />;
}
