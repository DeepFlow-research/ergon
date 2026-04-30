import { NextResponse } from "next/server";

import { emitHarnessRunCompleted } from "@/lib/testing/dashboardHarness";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    runId: string;
    status: "completed" | "failed";
    durationSeconds: number;
    finalScore: number | null;
    error: string | null;
    cohortId?: string | null;
  };
  emitHarnessRunCompleted(payload);
  return NextResponse.json({ ok: true });
}
