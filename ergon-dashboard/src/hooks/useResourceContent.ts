"use client";

/**
 * Fetches text content for a resource through the Next.js proxy (which in turn
 * calls GET /runs/{runId}/resources/{resourceId}/content on the Ergon API).
 * Responses are cached in a module-level Map so re-opening a viewer is free.
 */

import { useEffect, useState } from "react";

const textCache = new Map<string, string>();

export function resourceContentUrl(runId: string, resourceId: string): string {
  return `/api/runs/${runId}/resources/${resourceId}/content`;
}

interface UseResourceContentResult {
  text: string | null;
  error: string | null;
  isLoading: boolean;
}

export function useResourceContent(
  runId: string | null,
  resourceId: string | null,
  enabled: boolean,
): UseResourceContentResult {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!enabled || runId === null || resourceId === null) {
      setText(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    const cacheKey = `${runId}:${resourceId}`;
    const cached = textCache.get(cacheKey);
    if (cached !== undefined) {
      setText(cached);
      setError(null);
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    setText(null);

    fetch(resourceContentUrl(runId, resourceId), {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.text();
      })
      .then((body) => {
        textCache.set(cacheKey, body);
        setText(body);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load resource");
        setIsLoading(false);
      });

    return () => controller.abort();
  }, [runId, resourceId, enabled]);

  return { text, error, isLoading };
}
