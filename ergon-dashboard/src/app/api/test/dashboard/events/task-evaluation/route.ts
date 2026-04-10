import { NextResponse } from "next/server";

import { emitHarnessTaskEvaluation } from "@/lib/testing/dashboardHarness";
import { TaskEvaluationState } from "@/lib/types";

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    runId: string;
    taskId: string | null;
    evaluation: TaskEvaluationState;
  };
  emitHarnessTaskEvaluation(payload.runId, payload.taskId, payload.evaluation);
  return NextResponse.json({ ok: true });
}
