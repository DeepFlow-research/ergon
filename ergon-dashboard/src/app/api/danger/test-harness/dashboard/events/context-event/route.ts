import { NextResponse } from "next/server";

import { emitHarnessContextEvent } from "@/lib/testing/dashboardHarness";
import { ContextEventState } from "@/lib/types";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    runId: string;
    taskId: string;
    event: ContextEventState;
  };
  emitHarnessContextEvent(payload.runId, payload.taskId, payload.event);
  return NextResponse.json({ ok: true });
}
