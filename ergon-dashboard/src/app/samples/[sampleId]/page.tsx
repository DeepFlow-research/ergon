import { redirect } from "next/navigation";

interface SamplePageProps {
  params: Promise<{
    sampleId: string;
  }>;
}

export default async function SamplePage({ params }: SamplePageProps) {
  const { sampleId } = await params;
  redirect(`/samples/${sampleId}/detail`);
}
