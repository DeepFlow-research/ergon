import { CohortExperimentDetailView } from "@/components/cohorts/CohortExperimentDetailView";
import { loadCohortDetail } from "@/lib/server-data/cohorts";

interface CohortPageProps {
  params: Promise<{
    cohortId: string;
  }>;
}

export default async function CohortPage({ params }: CohortPageProps) {
  const { cohortId } = await params;
  let initialDetail = null;

  const result = await loadCohortDetail(cohortId);
  if (result.ok) {
    initialDetail = result.data;
  }

  return <CohortExperimentDetailView detail={initialDetail} />;
}
