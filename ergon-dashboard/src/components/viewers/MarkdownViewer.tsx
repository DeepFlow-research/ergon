"use client";

/**
 * Markdown viewer. Uses react-markdown + remark-gfm for GitHub-flavoured
 * markdown (tables, task lists, strikethrough). No dangerouslySetInnerHTML.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownViewerProps {
  text: string;
}

export function MarkdownViewer({ text }: MarkdownViewerProps) {
  return (
    <div className="prose prose-sm max-w-none px-6 py-5 dark:prose-invert prose-headings:text-gray-900 dark:prose-headings:text-white prose-a:text-blue-600 dark:prose-a:text-blue-400">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
