"use client";

import { useState, useEffect, useCallback, useRef } from "react";

export type BuildHealthStatus = "unknown" | "healthy" | "degraded";

interface HealthResponse {
  status: "healthy" | "degraded";
  checks: Record<string, "ok" | "fail">;
  errors?: string[];
  build: { nodeEnv: string; timestamp: string | null; pid: number };
}

interface BuildHealth {
  status: BuildHealthStatus;
  errors: string[];
  lastChecked: number | null;
  check: () => Promise<void>;
}

const POLL_INTERVAL_MS = 60_000;
const DEGRADED_RETRY_MS = 10_000;

export function useBuildHealth(): BuildHealth {
  const [status, setStatus] = useState<BuildHealthStatus>("unknown");
  const [errors, setErrors] = useState<string[]>([]);
  const [lastChecked, setLastChecked] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const check = useCallback(async () => {
    try {
      const res = await fetch("/api/health", {
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as Partial<HealthResponse>;
        setStatus("degraded");
        setErrors(body.errors ?? [`Health check returned ${res.status}`]);
      } else {
        const body = (await res.json()) as HealthResponse;
        setStatus(body.status === "healthy" ? "healthy" : "degraded");
        setErrors(body.errors ?? []);
      }
    } catch (e) {
      setStatus("degraded");
      setErrors([
        `Health check failed: ${e instanceof Error ? e.message : "network error"}. ` +
          "The dev server may need a restart (docker compose restart dashboard).",
      ]);
    }
    setLastChecked(Date.now());
  }, []);

  useEffect(() => {
    check();

    const schedule = () => {
      const interval = status === "degraded" ? DEGRADED_RETRY_MS : POLL_INTERVAL_MS;
      timerRef.current = setTimeout(async () => {
        await check();
        schedule();
      }, interval);
    };

    schedule();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [check, status]);

  return { status, errors, lastChecked, check };
}
