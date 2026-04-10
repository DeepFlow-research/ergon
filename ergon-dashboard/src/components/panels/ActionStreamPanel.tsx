"use client";

/**
 * ActionStreamPanel - Scrollable list of agent actions with live updates.
 *
 * Features:
 * - Timestamp, tool name, duration, status indicator
 * - Collapsible input/output JSON
 * - Auto-scroll to latest action
 */

import { useState, useEffect, useRef } from "react";
import { ActionState } from "@/lib/types";

interface ActionStreamPanelProps {
  actions: ActionState[];
  isLoading?: boolean;
  maxHeight?: string;
}

/**
 * Format duration in milliseconds to a readable string.
 */
function formatDuration(ms: number | null): string {
  if (ms === null) return "...";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

/**
 * Format timestamp to time string.
 */
function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * Try to parse and format JSON, or return the original string.
 */
function formatJson(jsonString: string | null): string {
  if (!jsonString) return "null";
  try {
    const parsed = JSON.parse(jsonString);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return jsonString;
  }
}

interface ActionItemProps {
  action: ActionState;
}

function ActionItem({ action }: ActionItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const statusColors = {
    started: "text-yellow-600 dark:text-yellow-400",
    completed: "text-green-600 dark:text-green-400",
    failed: "text-red-600 dark:text-red-400",
  };

  const statusIcons = {
    started: (
      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    ),
    completed: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    failed: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header row */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 flex items-center gap-3 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-left"
      >
        {/* Expand/collapse indicator */}
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? "rotate-90" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>

        {/* Timestamp */}
        <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
          {formatTime(action.startedAt)}
        </span>

        {/* Tool icon */}
        <span className="text-gray-400">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
        </span>

        {/* Tool name */}
        <span className="font-medium text-gray-900 dark:text-white flex-1 truncate">
          {action.type}
        </span>

        {/* Status */}
        <span className={`flex items-center gap-1 ${statusColors[action.status]}`}>
          {statusIcons[action.status]}
          <span className="text-xs">{formatDuration(action.durationMs)}</span>
        </span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-3 py-2 space-y-3 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          {/* Input */}
          <div>
            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span className="font-medium">Input</span>
            </div>
            <pre className="text-xs bg-gray-50 dark:bg-gray-800 rounded p-2 overflow-x-auto max-h-40 overflow-y-auto">
              <code className="text-gray-700 dark:text-gray-300">
                {formatJson(action.input)}
              </code>
            </pre>
          </div>

          {/* Output */}
          <div>
            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span className="font-medium">Output</span>
              {action.status === "started" && (
                <span className="text-yellow-600 dark:text-yellow-400">(in progress)</span>
              )}
            </div>
            {action.output ? (
              <pre className="text-xs bg-gray-50 dark:bg-gray-800 rounded p-2 overflow-x-auto max-h-40 overflow-y-auto">
                <code className="text-gray-700 dark:text-gray-300">
                  {formatJson(action.output)}
                </code>
              </pre>
            ) : action.status === "started" ? (
              <div className="text-xs text-gray-400 dark:text-gray-500 italic">
                Waiting for result...
              </div>
            ) : (
              <div className="text-xs text-gray-400 dark:text-gray-500 italic">
                No output
              </div>
            )}
          </div>

          {/* Error (if any) */}
          {action.error && (
            <div>
              <div className="flex items-center gap-2 text-xs text-red-500 mb-1">
                <span className="font-medium">Error</span>
              </div>
              <pre className="text-xs bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded p-2 overflow-x-auto">
                {action.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ActionStreamPanel({
  actions,
  isLoading = false,
  maxHeight = "400px",
}: ActionStreamPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom when new actions arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [actions.length, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  };

  if (actions.length === 0 && !isLoading) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
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
            d="M13 10V3L4 14h7v7l9-11h-7z"
          />
        </svg>
        <p>No actions yet</p>
        <p className="text-sm">Actions will appear as the worker executes</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Header with auto-scroll indicator */}
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{actions.length} action{actions.length !== 1 ? "s" : ""}</span>
        <button
          onClick={() => {
            setAutoScroll(true);
            if (scrollRef.current) {
              scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }
          }}
          className={`flex items-center gap-1 ${
            autoScroll ? "text-blue-500" : "text-gray-400 hover:text-gray-600"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
          Auto-scroll
        </button>
      </div>

      {/* Actions list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="space-y-2 overflow-y-auto pr-1"
        style={{ maxHeight }}
      >
        {actions.map((action) => (
          <ActionItem key={action.id} action={action} />
        ))}

        {isLoading && (
          <div className="flex items-center justify-center py-4 text-gray-500 dark:text-gray-400">
            <svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Loading...
          </div>
        )}
      </div>
    </div>
  );
}
