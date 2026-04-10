import { NextResponse } from "next/server";

import { emitHarnessThreadMessage } from "@/lib/testing/dashboardHarness";
import { CommunicationThreadState } from "@/lib/types";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    runId: string;
    thread: CommunicationThreadState;
  };
  emitHarnessThreadMessage(payload.runId, payload.thread);
  return NextResponse.json({ ok: true });
}
