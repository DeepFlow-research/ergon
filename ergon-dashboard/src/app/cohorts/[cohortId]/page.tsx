import { CohortExperimentDetailView } from "@/components/cohorts/CohortExperimentDetailView";
import { fetchErgonApi } from "@/lib/serverApi";

interface CohortPageProps {
  params: Promise<{
    cohortId: string;
  }>;
}

export default async function CohortPage({ params }: CohortPageProps) {
  const { cohortId } = await params;
  let initialDetail = null;

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`);
    if (response.ok) {
      initialDetail = await response.json();
    }
  } catch {
    initialDetail = null;
  }

  return <CohortExperimentDetailView detail={initialDetail} />;
}
