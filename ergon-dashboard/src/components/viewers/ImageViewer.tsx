"use client";

/**
 * Image viewer. Uses a plain <img>; contain-fit so portrait / landscape both
 * look sensible inside the dialog box.
 */

interface ImageViewerProps {
  url: string;
  name: string;
}

export function ImageViewer({ url, name }: ImageViewerProps) {
  return (
    <div className="flex h-[80vh] items-center justify-center bg-gray-50 p-6 dark:bg-gray-950">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={name}
        className="max-h-full max-w-full object-contain"
      />
    </div>
  );
}
