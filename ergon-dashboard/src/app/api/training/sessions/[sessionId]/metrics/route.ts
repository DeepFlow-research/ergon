import { NextRequest, NextResponse } from "next/server";
import { fetchErgonApi } from "@/lib/serverApi";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;

  try {
    const res = await fetchErgonApi(`/runs/training/sessions/${sessionId}/metrics`);
    if (!res.ok) {
      return NextResponse.json({ error: `Backend returned ${res.status}` }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Backend unreachable" },
      { status: 502 },
    );
  }
}
