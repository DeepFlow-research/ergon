import { CohortDetailView } from "@/components/cohorts/CohortDetailView";
import { parseCohortDetail } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import type { CohortDetail } from "@/lib/types";

interface CohortPageProps {
  params: Promise<{
    cohortId: string;
  }>;
}

export default async function CohortPage({ params }: CohortPageProps) {
  const { cohortId } = await params;
  let initialDetail: CohortDetail | null = null;

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`);
    if (response.ok) {
      initialDetail = parseCohortDetail(await response.json());
    }
  } catch {
    initialDetail = null;
  }

  return <CohortDetailView cohortId={cohortId} initialDetail={initialDetail} />;
}
