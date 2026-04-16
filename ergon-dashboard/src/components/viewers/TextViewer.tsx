"use client";

/**
 * Plain-text viewer: monospace <pre> with line numbers. Serves as the default
 * fallback for anything not matched by a more specific viewer (JSON, log files,
 * unknown mime types).
 */

interface TextViewerProps {
  text: string;
}

export function TextViewer({ text }: TextViewerProps) {
  const lines = text.split("\n");
  return (
    <pre className="font-mono text-xs leading-5 text-gray-900 dark:text-gray-100">
      <div className="flex">
        <div
          aria-hidden
          className="select-none border-r border-gray-200 bg-gray-50 px-3 py-3 text-right text-gray-400 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-600"
        >
          {lines.map((_, idx) => (
            <div key={idx}>{idx + 1}</div>
          ))}
        </div>
        <code className="flex-1 whitespace-pre-wrap break-words px-3 py-3">{text}</code>
      </div>
    </pre>
  );
}
