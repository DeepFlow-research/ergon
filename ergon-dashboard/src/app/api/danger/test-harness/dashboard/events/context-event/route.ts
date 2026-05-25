import { NextResponse } from "next/server";

import { emitHarnessContextEvent } from "@/lib/testing/dashboardHarness";
import { ContextEventState } from "@/lib/types";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    sampleId: string;
    taskId: string;
    event: ContextEventState;
  };
  emitHarnessContextEvent(payload.sampleId, payload.taskId, payload.event);
  return NextResponse.json({ ok: true });
}
