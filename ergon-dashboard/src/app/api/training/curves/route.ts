import { NextRequest, NextResponse } from "next/server";
import { fetchErgonApi } from "@/lib/serverApi";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const definitionId = searchParams.get("definition_id");
  const cohortId = searchParams.get("cohort_id");

  const params = new URLSearchParams();
  if (definitionId) params.set("definition_id", definitionId);
  if (cohortId) params.set("cohort_id", cohortId);

  const path = `/runs/training/curves?${params.toString()}`;

  try {
    const res = await fetchErgonApi(path);
    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend returned ${res.status}` },
        { status: res.status },
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Backend unreachable" },
      { status: 502 },
    );
  }
}
