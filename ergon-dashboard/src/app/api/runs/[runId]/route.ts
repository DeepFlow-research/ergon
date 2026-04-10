import { NextResponse } from "next/server";

import { config } from "@/lib/config";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRun } from "@/lib/testing/dashboardHarness";

interface RouteContext {
  params: Promise<{
    runId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { runId } = await context.params;

  if (config.enableTestHarness) {
    const run = getHarnessRun(runId);
    if (run === null) {
      return NextResponse.json({ detail: `Run ${runId} not found` }, { status: 404 });
    }
    return NextResponse.json(run);
  }

  try {
    const response = await fetchErgonApi(`/runs/${runId}`);
    const body = await response.json();
    if (response.ok) {
      return NextResponse.json(parseRunSnapshot(body), { status: response.status });
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while loading run ${runId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
