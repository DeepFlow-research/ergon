import { NextResponse } from "next/server";

import { DashboardHarnessSeedPayload, seedDashboardHarness } from "@/lib/testing/dashboardHarness";

export async function POST(request: Request) {
  const payload = (await request.json()) as DashboardHarnessSeedPayload;
  seedDashboardHarness(payload);
  return NextResponse.json({ ok: true });
}
