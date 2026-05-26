import { NextResponse } from "next/server";

import { loadRunSnapshot } from "@/lib/server-data/samples";

interface RouteContext {
  params: Promise<{
    sampleId: string;
  }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { sampleId } = await context.params;
  const result = await loadRunSnapshot(sampleId);

  if (result.ok) {
    return NextResponse.json(result.data, { status: result.status });
  }
  return NextResponse.json(result.body, { status: result.status });
}
