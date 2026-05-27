import { NextResponse } from "next/server";

import { fetchErgonApi } from "@/lib/serverApi";

interface RouteContext {
  params: Promise<{
    sampleId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { sampleId } = await context.params;

  try {
    const response = await fetchErgonApi(`/samples/${sampleId}/events`);
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while loading runtime events for sample ${sampleId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
