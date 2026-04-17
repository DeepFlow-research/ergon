"use client";

/**
 * PDF viewer. Uses a same-origin <iframe>; the browser's native PDF renderer
 * handles scrolling, zoom, printing, etc.
 */

interface PdfViewerProps {
  url: string;
  name: string;
}

export function PdfViewer({ url, name }: PdfViewerProps) {
  return (
    <iframe
      src={url}
      title={name}
      className="h-[80vh] w-full border-0 bg-white"
    />
  );
}
