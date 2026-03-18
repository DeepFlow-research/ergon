"use client";

/**
 * SandboxPanel - E2B sandbox visibility.
 *
 * Features:
 * - Sandbox ID, template, status, timeout
 * - Command history with stdout/stderr
 * - Exit codes and duration
 * - Active/closed indicator
 */

import { useState } from "react";
import { SandboxState, SandboxCommandState } from "@/lib/types";

interface SandboxPanelProps {
  sandbox: SandboxState | undefined;
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

interface CommandItemProps {
  command: SandboxCommandState;
}

function CommandItem({ command }: CommandItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasOutput = command.stdout || command.stderr;
  const exitCodeColor =
    command.exitCode === 0
      ? "text-green-600 dark:text-green-400"
      : command.exitCode !== null
        ? "text-red-600 dark:text-red-400"
        : "text-yellow-600 dark:text-yellow-400";

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden font-mono text-sm">
      {/* Command header */}
      <button
        onClick={() => hasOutput && setIsExpanded(!isExpanded)}
        className={`w-full px-3 py-2 flex items-center gap-2 bg-gray-900 dark:bg-gray-950 text-left ${
          hasOutput ? "cursor-pointer hover:bg-gray-800" : "cursor-default"
        }`}
        disabled={!hasOutput}
      >
        {/* Expand indicator */}
        {hasOutput && (
          <svg
            className={`w-3 h-3 text-gray-500 transition-transform ${isExpanded ? "rotate-90" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        )}

        {/* Prompt */}
        <span className="text-green-400">$</span>

        {/* Command */}
        <span className="text-gray-200 flex-1 truncate">{command.command}</span>

        {/* Duration and exit code */}
        <span className="flex items-center gap-2 text-xs">
          {command.durationMs !== null && (
            <span className="text-gray-500">{formatDuration(command.durationMs)}</span>
          )}
          {command.exitCode !== null ? (
            <span className={exitCodeColor}>exit {command.exitCode}</span>
          ) : (
            <span className="text-yellow-500 animate-pulse">running...</span>
          )}
        </span>
      </button>

      {/* Output (expanded) */}
      {isExpanded && hasOutput && (
        <div className="bg-gray-950 border-t border-gray-800">
          {command.stdout && (
            <div className="px-3 py-2">
              <pre className="text-gray-300 whitespace-pre-wrap text-xs overflow-x-auto max-h-40 overflow-y-auto">
                {command.stdout}
              </pre>
            </div>
          )}
          {command.stderr && (
            <div className="px-3 py-2 bg-red-950/30">
              <div className="text-xs text-red-400 mb-1">stderr:</div>
              <pre className="text-red-300 whitespace-pre-wrap text-xs overflow-x-auto max-h-40 overflow-y-auto">
                {command.stderr}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SandboxPanel({ sandbox }: SandboxPanelProps) {
  if (!sandbox) {
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
            d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
        <p>No sandbox</p>
        <p className="text-sm">This task does not use a sandbox</p>
      </div>
    );
  }

  const isActive = sandbox.status === "active";

  return (
    <div className="space-y-4">
      {/* Sandbox info */}
      <div className="flex items-center justify-between bg-gray-50 dark:bg-gray-800/50 rounded-lg px-3 py-2">
        <div className="flex items-center gap-3">
          {/* Status indicator */}
          <div className="relative">
            <div
              className={`w-3 h-3 rounded-full ${
                isActive ? "bg-green-500" : "bg-gray-400"
              }`}
            />
            {isActive && (
              <div className="absolute inset-0 w-3 h-3 rounded-full bg-green-500 animate-ping opacity-50" />
            )}
          </div>

          {/* Info */}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-900 dark:text-white">
                {isActive ? "Active" : "Closed"}
              </span>
              {sandbox.template && (
                <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                  {sandbox.template}
                </span>
              )}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
              {sandbox.sandboxId.slice(0, 12)}...
            </div>
          </div>
        </div>

        {/* Timeout/Close reason */}
        <div className="text-right text-xs text-gray-500 dark:text-gray-400">
          {isActive ? (
            <span>Timeout: {sandbox.timeoutMinutes}m</span>
          ) : (
            <span>
              Closed: {sandbox.closeReason}
              {sandbox.closedAt && (
                <span className="block">{formatTime(sandbox.closedAt)}</span>
              )}
            </span>
          )}
        </div>
      </div>

      {/* Command history */}
      <div>
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-2">
          <span>Commands ({sandbox.commands.length})</span>
          <span>Created: {formatTime(sandbox.createdAt)}</span>
        </div>

        {sandbox.commands.length === 0 ? (
          <div className="text-center py-4 text-gray-500 dark:text-gray-400 text-sm">
            No commands executed yet
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {sandbox.commands.map((cmd, idx) => (
              <CommandItem key={`${cmd.timestamp}-${idx}`} command={cmd} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
