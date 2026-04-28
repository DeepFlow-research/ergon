import { CohortExperimentDetailView } from "@/components/cohorts/CohortExperimentDetailView";
import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessCohort } from "@/lib/testing/dashboardHarness";

interface CohortPageProps {
  params: Promise<{
    cohortId: string;
  }>;
}

export default async function CohortPage({ params }: CohortPageProps) {
  const { cohortId } = await params;
  let initialDetail = null;

  try {
    if (config.enableTestHarness) {
      initialDetail = getHarnessCohort(cohortId);
    } else {
      const response = await fetchErgonApi(`/cohorts/${cohortId}`);
      if (response.ok) {
        initialDetail = await response.json();
      }
    }
  } catch {
    initialDetail = null;
  }

  return <CohortExperimentDetailView detail={initialDetail} />;
}
