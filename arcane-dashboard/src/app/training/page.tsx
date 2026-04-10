"use client";

import { useEffect, useState } from "react";
import {
  TrainingCurveChart,
  type CurveDataPoint,
} from "@/components/charts/TrainingCurveChart";
import {
  TrainingMetricsChart,
  type MetricPoint,
} from "@/components/charts/TrainingMetricsChart";

interface TrainingSessionSummary {
  id: string;
  model_name: string;
  status: string;
  started_at: string | null;
  total_steps: number | null;
  final_loss: number | null;
}

export default function TrainingPage() {
  const [sessions, setSessions] = useState<TrainingSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [metrics, setMetrics] = useState<MetricPoint[]>([]);
  const [evalCurve, setEvalCurve] = useState<CurveDataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/training/sessions", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: TrainingSessionSummary[]) => {
        setSessions(data);
        if (data.length > 0 && !selectedSessionId) {
          setSelectedSessionId(data[0].id);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load sessions");
        setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedSessionId) {
      setMetrics([]);
      return;
    }

    setError(null);
    fetch(`/api/training/sessions/${selectedSessionId}/metrics`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: MetricPoint[]) => setMetrics(data))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load metrics"));

    const session = sessions.find((s) => s.id === selectedSessionId);
    if (session) {
      fetch(`/api/training/curves?definition_id=${selectedSessionId}`, { cache: "no-store" })
        .then(async (res) => {
          if (!res.ok) return [];
          return res.json();
        })
        .then((data: CurveDataPoint[]) => setEvalCurve(data))
        .catch(() => setEvalCurve([]));
    }
  }, [selectedSessionId, sessions]);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Training
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Training metrics and checkpoint evaluation scores.
        </p>
      </header>

      {isLoading && (
        <div className="flex h-32 items-center justify-center text-sm text-gray-500">
          Loading sessions...
        </div>
      )}

      {!isLoading && sessions.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center dark:border-gray-700 dark:bg-gray-900">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No training sessions found. Run <code className="rounded bg-gray-100 px-1 dark:bg-gray-800">arcane train local</code> to start one.
          </p>
        </div>
      )}

      {sessions.length > 0 && (
        <>
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label
                htmlFor="session-select"
                className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400"
              >
                Training Session
              </label>
              <select
                id="session-select"
                value={selectedSessionId}
                onChange={(e) => setSelectedSessionId(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              >
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.model_name} ({s.status}) — {s.total_steps ?? "?"} steps
                    {s.started_at ? ` — ${new Date(s.started_at).toLocaleString()}` : ""}
                  </option>
                ))}
              </select>
            </div>
            {selectedSession && (
              <div className="flex gap-3 text-xs text-gray-500 dark:text-gray-400">
                <span className={`rounded-full px-2 py-1 font-medium ${
                  selectedSession.status === "completed"
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : selectedSession.status === "failed"
                      ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                      : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                }`}>
                  {selectedSession.status}
                </span>
                {selectedSession.final_loss != null && (
                  <span>Loss: {selectedSession.final_loss.toFixed(6)}</span>
                )}
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          )}

          <section className="rounded-2xl border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Training Metrics
            </h2>
            <TrainingMetricsChart data={metrics} />
            {metrics.length > 0 && (
              <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
                {metrics.length} step{metrics.length === 1 ? "" : "s"} logged
              </p>
            )}
          </section>

          <section className="rounded-2xl border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Checkpoint Evaluation Scores
            </h2>
            <TrainingCurveChart data={evalCurve} />
          </section>
        </>
      )}
    </main>
  );
}
