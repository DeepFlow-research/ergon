import { NextResponse } from "next/server";

import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";

interface RouteContext {
  params: Promise<{
    runId: string;
    resourceId: string;
  }>;
}

/**
 * Proxy the binary-or-text body of a RunResource blob from the Ergon API back
 * to the dashboard. No parsing — we preserve Content-Type and
 * Content-Disposition so viewers (markdown, PDF via iframe, image, CSV) can
 * interpret the stream themselves.
 */
export async function GET(_request: Request, context: RouteContext) {
  const { runId, resourceId } = await context.params;

  if (config.enableTestHarness) {
    // The test harness doesn't persist resources; surface a 404 so viewers
    // render a "not found" state rather than a cryptic proxy error.
    return NextResponse.json(
      { detail: "Resource content unavailable in test harness mode" },
      { status: 404 },
    );
  }

  try {
    const upstream = await fetchErgonApi(`/runs/${runId}/resources/${resourceId}/content`, {
      headers: {
        Accept: "*/*",
      },
    });

    // Forward the body and key headers as-is. Don't blindly copy every
    // upstream header — transfer-encoding in particular breaks Next.
    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    const contentDisposition = upstream.headers.get("content-disposition");
    const contentLength = upstream.headers.get("content-length");
    if (contentType) headers.set("content-type", contentType);
    if (contentDisposition) headers.set("content-disposition", contentDisposition);
    if (contentLength) headers.set("content-length", contentLength);
    headers.set("cache-control", "no-store");

    return new Response(upstream.body, {
      status: upstream.status,
      headers,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: `Ergon API is unavailable while loading resource ${resourceId}.`,
        error: error instanceof Error ? error.message : "Unknown backend fetch failure",
      },
      { status: 503 },
    );
  }
}
