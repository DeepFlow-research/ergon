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

export interface CurveDataPoint {
  step: number;
  meanScore: number;
  benchmarkType: string | null;
  createdAt: string | null;
  runId: string;
}

interface TrainingCurveChartProps {
  data: CurveDataPoint[];
  height?: number;
}

const COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
  "#06b6d4", "#f97316", "#84cc16",
];

function formatScore(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function TrainingCurveChart({ data, height = 360 }: TrainingCurveChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        No checkpoint evaluation data available yet.
      </div>
    );
  }

  const benchmarks = Array.from(new Set(data.map((d) => d.benchmarkType ?? "unknown")));
  const isSingleBenchmark = benchmarks.length === 1;

  if (isSingleBenchmark) {
    const sorted = [...data].sort((a, b) => a.step - b.step);
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={sorted} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis
            dataKey="step"
            label={{ value: "Training Step", position: "insideBottom", offset: -4, fontSize: 12 }}
            fontSize={11}
          />
          <YAxis
            tickFormatter={formatScore}
            label={{ value: "Score", angle: -90, position: "insideLeft", fontSize: 12 }}
            fontSize={11}
            domain={[0, 1]}
          />
          <Tooltip
            formatter={(value) => [formatScore(Number(value)), "Score"]}
            labelFormatter={(step) => `Step ${step}`}
          />
          <Line
            type="monotone"
            dataKey="meanScore"
            stroke={COLORS[0]}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            name={benchmarks[0]}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  const pivoted = new Map<number, Record<string, number>>();
  for (const d of data) {
    const key = d.benchmarkType ?? "unknown";
    const existing = pivoted.get(d.step) ?? { step: d.step };
    existing[key] = d.meanScore;
    pivoted.set(d.step, existing);
  }
  const chartData = Array.from(pivoted.values()).sort(
    (a, b) => (a.step as number) - (b.step as number),
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis
          dataKey="step"
          label={{ value: "Training Step", position: "insideBottom", offset: -4, fontSize: 12 }}
          fontSize={11}
        />
        <YAxis
          tickFormatter={formatScore}
          label={{ value: "Score", angle: -90, position: "insideLeft", fontSize: 12 }}
          fontSize={11}
          domain={[0, 1]}
        />
        <Tooltip formatter={(value) => formatScore(Number(value))} />
        <Legend />
        {benchmarks.map((bm, i) => (
          <Line
            key={bm}
            type="monotone"
            dataKey={bm}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            name={bm}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
