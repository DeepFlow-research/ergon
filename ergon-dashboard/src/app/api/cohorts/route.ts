import { NextResponse } from "next/server";

import { config } from "@/lib/config";
import { parseCohortSummaryList } from "@/lib/contracts/rest";
import { fetchArcaneApi } from "@/lib/serverApi";
import { listHarnessCohorts } from "@/lib/testing/dashboardHarness";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const includeArchived = url.searchParams.get("includeArchived");
  const backendPath =
    includeArchived === null ? "/cohorts" : `/cohorts?include_archived=${includeArchived}`;

  if (config.enableTestHarness) {
    return NextResponse.json(listHarnessCohorts());
  }

  try {
    const response = await fetchArcaneApi(backendPath);
    const body = await response.json();
    if (response.ok) {
      return NextResponse.json(parseCohortSummaryList(body), { status: response.status });
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Arcane API is unavailable while loading cohorts.",
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
