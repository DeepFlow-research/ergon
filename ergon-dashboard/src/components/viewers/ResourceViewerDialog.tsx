"use client";

/**
 * Dialog wrapper that owns viewer dispatch and content-fetch for one selected
 * resource. Mount once per panel; `resource` drives open/close.
 */

import { Dialog } from "@/components/ui/Dialog";
import { CsvViewer } from "@/components/viewers/CsvViewer";
import { ImageViewer } from "@/components/viewers/ImageViewer";
import { MarkdownViewer } from "@/components/viewers/MarkdownViewer";
import { PdfViewer } from "@/components/viewers/PdfViewer";
import { TextViewer } from "@/components/viewers/TextViewer";
import { resolveViewerKind, viewerWantsText } from "@/components/viewers";
import { resourceContentUrl, useResourceContent } from "@/hooks/useResourceContent";
import type { ResourceState } from "@/lib/types";

interface ResourceViewerDialogProps {
  runId: string | null;
  resource: ResourceState | null;
  onClose: () => void;
}

export function ResourceViewerDialog({ runId, resource, onClose }: ResourceViewerDialogProps) {
  const open = resource !== null && runId !== null;
  const kind = resource ? resolveViewerKind(resource.mimeType) : "text";
  const wantsText = viewerWantsText(kind);

  const { text, error, isLoading } = useResourceContent(
    runId,
    resource?.id ?? null,
    open && wantsText,
  );

  return (
    <Dialog open={open} onClose={onClose} title={resource?.name}>
      {resource === null || runId === null ? null : (
        <ViewerBody
          runId={runId}
          resource={resource}
          text={text}
          error={error}
          isLoading={isLoading}
        />
      )}
    </Dialog>
  );
}

function ViewerBody({
  runId,
  resource,
  text,
  error,
  isLoading,
}: {
  runId: string;
  resource: ResourceState;
  text: string | null;
  error: string | null;
  isLoading: boolean;
}) {
  const kind = resolveViewerKind(resource.mimeType);
  const url = resourceContentUrl(runId, resource.id);

  if (error !== null) {
    return (
      <div className="px-6 py-5 text-sm text-red-600 dark:text-red-400">
        Failed to load resource: {error}
      </div>
    );
  }

  if (kind === "pdf") {
    return <PdfViewer url={url} name={resource.name} />;
  }
  if (kind === "image") {
    return <ImageViewer url={url} name={resource.name} />;
  }

  if (isLoading || text === null) {
    return (
      <div className="px-6 py-5 text-sm text-gray-500 dark:text-gray-400">Loading…</div>
    );
  }

  if (kind === "markdown") {
    return <MarkdownViewer text={text} />;
  }
  if (kind === "csv") {
    return <CsvViewer text={text} />;
  }
  return <TextViewer text={text} />;
}
