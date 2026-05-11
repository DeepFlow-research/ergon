import { NextResponse } from "next/server";

import { resetDashboardHarness } from "@/lib/testing/dashboardHarness";

// Next.js treats underscore-prefixed App Router segments as private, so these
// dashboard-only test routes intentionally live under /api/danger rather than
// the backend's /api/__danger__ namespace.
export async function POST() {
  resetDashboardHarness();
  return NextResponse.json({ ok: true });
}
