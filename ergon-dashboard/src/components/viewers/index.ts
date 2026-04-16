/**
 * Viewer dispatcher: mime-type -> viewer kind. Keep this small and boring;
 * anything we don't recognise falls through to the text viewer, which renders
 * JSON, logs, configs, etc. adequately.
 */

export type ViewerKind = "markdown" | "text" | "pdf" | "image" | "csv";

export function resolveViewerKind(mimeType: string): ViewerKind {
  const mt = mimeType.toLowerCase();
  if (mt === "text/markdown" || mt === "text/x-markdown") return "markdown";
  if (mt === "application/pdf") return "pdf";
  if (mt.startsWith("image/")) return "image";
  if (mt === "text/csv" || mt === "application/csv") return "csv";
  return "text";
}

/**
 * Whether the viewer consumes text content (fetched as a string) or a URL
 * pointing at the content endpoint (embedded directly).
 */
export function viewerWantsText(kind: ViewerKind): boolean {
  return kind === "markdown" || kind === "text" || kind === "csv";
}
