"use client";

/**
 * ResourcePanel - Display input and output resources for a task.
 *
 * Features:
 * - File name, size (formatted), mime type icon
 * - Created timestamp
 * - Future: download/preview links
 */

import { ResourceState } from "@/lib/types";

interface ResourcePanelProps {
  resources: ResourceState[];
}

/**
 * Format file size to human-readable string.
 */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Format timestamp to relative time.
 */
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) return "just now";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return time.toLocaleDateString();
}

/**
 * Get icon for mime type.
 */
function getMimeTypeIcon(mimeType: string): JSX.Element {
  if (mimeType.startsWith("image/")) {
    return (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
        />
      </svg>
    );
  }

  if (mimeType.includes("json") || mimeType.includes("javascript")) {
    return (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
        />
      </svg>
    );
  }

  if (mimeType.includes("text") || mimeType.includes("markdown")) {
    return (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    );
  }

  if (mimeType.includes("pdf")) {
    return (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
        />
      </svg>
    );
  }

  // Default file icon
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  );
}

/**
 * Get color for mime type.
 */
function getMimeTypeColor(mimeType: string): string {
  if (mimeType.startsWith("image/")) {
    return "text-purple-500 dark:text-purple-400";
  }
  if (mimeType.includes("json") || mimeType.includes("javascript")) {
    return "text-yellow-500 dark:text-yellow-400";
  }
  if (mimeType.includes("text") || mimeType.includes("markdown")) {
    return "text-blue-500 dark:text-blue-400";
  }
  if (mimeType.includes("pdf")) {
    return "text-red-500 dark:text-red-400";
  }
  return "text-gray-500 dark:text-gray-400";
}

interface ResourceItemProps {
  resource: ResourceState;
}

function ResourceItem({ resource }: ResourceItemProps) {
  const iconColor = getMimeTypeColor(resource.mimeType);

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
      {/* Icon */}
      <div className={iconColor}>{getMimeTypeIcon(resource.mimeType)}</div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-gray-900 dark:text-white truncate">
          {resource.name}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span>{formatFileSize(resource.sizeBytes)}</span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="truncate">{resource.mimeType}</span>
        </div>
      </div>

      {/* Timestamp */}
      <div className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
        {formatRelativeTime(resource.createdAt)}
      </div>
    </div>
  );
}

export function ResourcePanel({ resources }: ResourcePanelProps) {
  if (resources.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500 dark:text-gray-400">
        <svg
          className="w-8 h-8 mx-auto mb-2 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"
          />
        </svg>
        <p>No resources</p>
        <p className="text-sm">Resources will appear as they are created</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
        {resources.length} resource{resources.length !== 1 ? "s" : ""}
      </div>
      <div className="space-y-2">
        {resources.map((resource) => (
          <ResourceItem key={resource.id} resource={resource} />
        ))}
      </div>
    </div>
  );
}
