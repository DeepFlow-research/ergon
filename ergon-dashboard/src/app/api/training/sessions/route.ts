import { NextRequest, NextResponse } from "next/server";
import { fetchErgonApi } from "@/lib/serverApi";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const definitionId = searchParams.get("definition_id");

  const params = new URLSearchParams();
  if (definitionId) params.set("definition_id", definitionId);

  const path = `/runs/training/sessions?${params.toString()}`;

  try {
    const res = await fetchErgonApi(path);
    if (!res.ok) {
      return NextResponse.json({ error: `Backend returned ${res.status}` }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json(
      {
        detail: "Ergon API is unavailable while loading training sessions.",
        error: err instanceof Error ? err.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
