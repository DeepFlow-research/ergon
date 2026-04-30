import { NextResponse } from "next/server";

import { parseUpdateCohortRequest } from "@/lib/contracts/rest";
import { loadCohortDetail, updateCohortStatus } from "@/lib/server-data/cohorts";

interface RouteContext {
  params: Promise<{
    cohortId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { cohortId } = await context.params;
  const result = await loadCohortDetail(cohortId);

  if (result.ok) {
    return NextResponse.json(result.data, { status: result.status });
  }
  return NextResponse.json(result.body, { status: result.status });
}

export async function PATCH(request: Request, context: RouteContext) {
  const { cohortId } = await context.params;
  let body;
  try {
    body = parseUpdateCohortRequest(await request.json());
  } catch {
    return NextResponse.json({ detail: "Invalid cohort status" }, { status: 400 });
  }

  if (body.status !== "active" && body.status !== "archived") {
    return NextResponse.json({ detail: "Invalid cohort status" }, { status: 400 });
  }

  const result = await updateCohortStatus(cohortId, body.status);

  if (result.ok) {
    return NextResponse.json(result.data, { status: result.status });
  }
  return NextResponse.json(result.body, { status: result.status });
}
