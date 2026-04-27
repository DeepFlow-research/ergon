import { NextResponse } from "next/server";

import { config } from "@/lib/config";
import {
  parseCohortSummary,
  parseUpdateCohortRequest,
} from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessCohort, updateHarnessCohortStatus } from "@/lib/testing/dashboardHarness";

interface RouteContext {
  params: Promise<{
    cohortId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { cohortId } = await context.params;

  if (config.enableTestHarness) {
    const detail = getHarnessCohort(cohortId);
    if (detail === null) {
      return NextResponse.json({ detail: `Cohort ${cohortId} not found` }, { status: 404 });
    }
    return NextResponse.json(detail);
  }

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`);
    const body = await response.json();
    if (response.ok) {
      return NextResponse.json(body, { status: response.status });
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while loading cohort ${cohortId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
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

  if (config.enableTestHarness) {
    const updated = updateHarnessCohortStatus(cohortId, body.status);
    if (updated === null) {
      return NextResponse.json({ detail: `Cohort ${cohortId} not found` }, { status: 404 });
    }
    return NextResponse.json(updated);
  }

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`, {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ status: body.status }),
    });
    const payload = await response.json();
    if (response.ok) {
      return NextResponse.json(parseCohortSummary(payload), { status: response.status });
    }
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while updating cohort ${cohortId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
