"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface MetricPoint {
  step: number;
  loss: number | null;
  grad_norm: number | null;
  learning_rate: number | null;
  reward_mean: number | null;
  reward_std: number | null;
  entropy: number | null;
  completion_mean_length: number | null;
  step_time_s: number | null;
}

interface TrainingMetricsChartProps {
  data: MetricPoint[];
  height?: number;
}

const METRICS = [
  { key: "loss", label: "Loss", color: "#ef4444" },
  { key: "reward_mean", label: "Reward", color: "#10b981" },
  { key: "entropy", label: "Entropy", color: "#6366f1" },
  { key: "grad_norm", label: "Grad Norm", color: "#f59e0b" },
] as const;

export function TrainingMetricsChart({ data, height = 360 }: TrainingMetricsChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        No training metrics available yet.
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => a.step - b.step);

  const activeMetrics = METRICS.filter((m) =>
    sorted.some((d) => (d as unknown as Record<string, unknown>)[m.key] != null),
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={sorted} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis
          dataKey="step"
          label={{ value: "Training Step", position: "insideBottom", offset: -4, fontSize: 12 }}
          fontSize={11}
        />
        <YAxis fontSize={11} />
        <Tooltip labelFormatter={(step) => `Step ${step}`} />
        <Legend />
        {activeMetrics.map((m) => (
          <Line
            key={m.key}
            type="monotone"
            dataKey={m.key}
            stroke={m.color}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            name={m.label}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
