import { NextResponse } from "next/server";

import { loadRunSnapshot } from "@/lib/server-data/runs";

interface RouteContext {
  params: Promise<{
    runId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { runId } = await context.params;
  const result = await loadRunSnapshot(runId);

  if (result.ok) {
    return NextResponse.json(result.data, { status: result.status });
  }
  return NextResponse.json(result.body, { status: result.status });
}
