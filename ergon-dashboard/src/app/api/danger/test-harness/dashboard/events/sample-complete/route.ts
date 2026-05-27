import { NextResponse } from "next/server";

import { emitHarnessSampleCompleted } from "@/lib/testing/dashboardHarness";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    sampleId: string;
    status: "completed" | "failed";
    durationSeconds: number;
    finalScore: number | null;
    error: string | null;
  };
  emitHarnessSampleCompleted(payload);
  return NextResponse.json({ ok: true });
}
