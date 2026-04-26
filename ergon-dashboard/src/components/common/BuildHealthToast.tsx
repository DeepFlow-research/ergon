"use client";

import { useState } from "react";
import { useBuildHealth } from "@/hooks/useBuildHealth";

export function BuildHealthToast() {
  const { status, errors, check } = useBuildHealth();
  const [dismissed, setDismissed] = useState(false);

  if (status !== "degraded" || dismissed) return null;

  const hasSSRFailure = errors.some(
    (e) => e.includes("SSR import") || e.includes("Cannot find module"),
  );
  const hasApiFailure = errors.some((e) => e.includes("Ergon API"));

  let headline: string;
  let advice: string;

  if (hasSSRFailure) {
    headline = "Stale build detected";
    advice =
      "The Next.js dev server has a corrupted cache. " +
      "Run: rm -rf .next && docker compose restart dashboard";
  } else if (hasApiFailure) {
    headline = "Backend API unreachable";
    advice =
      "The Ergon API is not responding. Check that the API container is running: " +
      "docker compose ps api";
  } else {
    headline = "Dashboard health degraded";
    advice = errors[0] ?? "Unknown issue — check server logs.";
  }

  return (
    <div
      data-testid="build-health-toast"
      className="fixed bottom-16 left-1/2 z-50 flex max-w-lg -translate-x-1/2 items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-5 py-3 shadow-lg"
    >
      <svg
        className="mt-0.5 size-5 shrink-0 text-red-500"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-red-800" data-testid="health-headline">
          {headline}
        </p>
        <p className="mt-0.5 text-xs text-red-700">{advice}</p>
        {errors.length > 1 && (
          <details className="mt-1.5">
            <summary className="cursor-pointer text-[10px] font-medium text-red-600">
              {errors.length} details
            </summary>
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-[10px] text-red-600">
              {errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <div className="flex shrink-0 gap-1.5">
        <button
          onClick={() => check()}
          className="rounded border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
          data-testid="health-retry"
        >
          Retry
        </button>
        <button
          onClick={() => setDismissed(true)}
          className="rounded px-2 py-1 text-xs text-red-500 hover:text-red-700"
          aria-label="Dismiss"
          data-testid="health-dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
