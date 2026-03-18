"use client";

/**
 * Home Page - Displays the list of workflow runs.
 *
 * Path: /
 */

import { RunListPanel } from "@/components/panels/RunListPanel";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                Arcane Dashboard
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Real-time workflow monitoring
              </p>
            </div>

            {/* Connection indicator */}
            <div className="flex items-center gap-2 text-sm">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              <span className="text-gray-500 dark:text-gray-400">Live</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <RunListPanel />
      </main>
    </div>
  );
}
