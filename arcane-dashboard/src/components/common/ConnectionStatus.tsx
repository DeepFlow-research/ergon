"use client";

/**
 * ConnectionStatus - Banner showing socket connection status.
 *
 * Shows a banner when disconnected or having connection issues,
 * with a retry button.
 */

import { useSocket, ConnectionStatus as Status } from "@/providers/SocketProvider";

export function ConnectionStatus() {
  const { connectionStatus, connectionError, reconnect } = useSocket();

  // Don't show anything when connected
  if (connectionStatus === "connected") {
    return null;
  }

  const statusConfig: Record<Status, { bg: string; text: string; icon: JSX.Element }> = {
    connecting: {
      bg: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
      text: "text-blue-700 dark:text-blue-300",
      icon: (
        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
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
    },
    connected: {
      bg: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
      text: "text-green-700 dark:text-green-300",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ),
    },
    disconnected: {
      bg: "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800",
      text: "text-yellow-700 dark:text-yellow-300",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      ),
    },
    error: {
      bg: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
      text: "text-red-700 dark:text-red-300",
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      ),
    },
  };

  const config = statusConfig[connectionStatus];

  const statusMessages: Record<Status, string> = {
    connecting: "Connecting to server...",
    connected: "Connected",
    disconnected: "Disconnected from server",
    error: "Connection error",
  };

  return (
    <div
      className={`
        fixed bottom-4 left-1/2 -translate-x-1/2 z-50
        flex items-center gap-3 px-4 py-2 rounded-lg border shadow-lg
        ${config.bg} ${config.text}
      `}
    >
      {config.icon}
      <span className="text-sm font-medium">
        {connectionError || statusMessages[connectionStatus]}
      </span>
      {(connectionStatus === "disconnected" || connectionStatus === "error") && (
        <button
          onClick={reconnect}
          className="ml-2 px-3 py-1 text-sm font-medium bg-white dark:bg-gray-800 rounded border border-current hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
