import { NextResponse } from "next/server";

import { resetDashboardHarness } from "@/lib/testing/dashboardHarness";

export async function POST() {
  resetDashboardHarness();
  return NextResponse.json({ ok: true });
}
