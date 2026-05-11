import { NextResponse } from "next/server";

import { loadCohortList } from "@/lib/server-data/cohorts";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const includeArchived = url.searchParams.get("includeArchived");
  const result = await loadCohortList(includeArchived);

  if (result.ok) {
    return NextResponse.json(result.data, { status: result.status });
  }
  return NextResponse.json(result.body, { status: result.status });
}
