import { NextResponse } from "next/server";

import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRunMutations } from "@/lib/testing/dashboardHarness";

interface RouteContext {
  params: Promise<{
    sampleId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { sampleId } = await context.params;

  try {
    if (config.enableTestHarness) {
      const harnessMutations = getHarnessRunMutations(sampleId);
      if (harnessMutations) {
        return NextResponse.json(harnessMutations);
      }
    }
    const response = await fetchErgonApi(`/samples/${sampleId}/mutations`);
    const body = await response.json();
    if (response.ok) {
      return NextResponse.json(body, { status: response.status });
    }
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while loading mutations for run ${sampleId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
