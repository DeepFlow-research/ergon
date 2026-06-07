"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  availableMetricPoints,
  formatRunMetricValue,
  metricDescriptor,
  percentile,
  RUN_METRIC_DESCRIPTORS,
  selectSampleRunMetricExplorerView,
  type SampleRunMetricExplorerMode,
  type RunMetricKey,
  type RunMetricPoint,
} from "./sampleRunMetricExplorerModel";

interface SampleRunMetricExplorerProps {
  points: RunMetricPoint[];
  runHrefBase?: string;
  initialMode?: SampleRunMetricExplorerMode;
  initialPrimaryMetric?: RunMetricKey;
  initialSecondaryMetric?: RunMetricKey;
}

const CHART_WIDTH = 640;
const CHART_HEIGHT = 260;
const CHART_PAD = 28;

function extent(values: number[]): [number, number] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [min - 1, max + 1];
  return [min, max];
}

function scale(value: number, min: number, max: number, outputMin: number, outputMax: number) {
  return outputMin + ((value - min) / (max - min)) * (outputMax - outputMin);
}

function runHref(runHrefBase: string, sampleId: string) {
  return `${runHrefBase.replace(/\/$/, "")}/${sampleId}`;
}

function HoverCard({
  point,
  primaryMetricKey,
  secondaryMetricKey,
}: {
  point: RunMetricPoint | null;
  primaryMetricKey: RunMetricKey;
  secondaryMetricKey: RunMetricKey;
}) {
  if (!point) {
    return (
      <div className="rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] bg-[var(--paper)] p-3 text-xs text-[var(--muted)]">
        Hover a run to inspect status, sample, model, evaluator, and plotted values.
      </div>
    );
  }

  const primary = metricDescriptor(primaryMetricKey);
  const secondary = metricDescriptor(secondaryMetricKey);
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] p-3 text-xs">
      <div className="flex items-center justify-between gap-3">
        <div className="font-mono text-[var(--ink)]">{point.runName}</div>
        <div className="text-[var(--muted)]">{point.status}</div>
      </div>
      <div className="mt-2 grid gap-1 text-[var(--muted)] sm:grid-cols-2">
        <div>Sample: <span className="text-[var(--ink)]">{point.sampleLabel}</span></div>
        <div>{primary.label}: <span className="text-[var(--ink)]">{formatRunMetricValue(primary, point.metrics[primaryMetricKey])}</span></div>
        <div>{secondary.label}: <span className="text-[var(--ink)]">{formatRunMetricValue(secondary, point.metrics[secondaryMetricKey])}</span></div>
        <div>Model: <span className="text-[var(--ink)]">{point.modelTarget ?? "Unavailable"}</span></div>
        <div>Evaluator: <span className="text-[var(--ink)]">{point.evaluatorSlug ?? "Unavailable"}</span></div>
        <div>Error: <span className="text-[var(--ink)]">{point.errorSummary ?? "None"}</span></div>
      </div>
    </div>
  );
}

function RankedList({
  points,
  metricKey,
  runHrefBase,
  onHover,
}: {
  points: RunMetricPoint[];
  metricKey: RunMetricKey;
  runHrefBase: string;
  onHover: (point: RunMetricPoint | null) => void;
}) {
  const descriptor = metricDescriptor(metricKey);
  const sorted = [...points].sort((a, b) => (b.metrics[metricKey].value ?? 0) - (a.metrics[metricKey].value ?? 0));

  return (
    <div className="grid gap-2">
      {sorted.map((point, index) => (
        <Link
          href={runHref(runHrefBase, point.sampleId)}
          key={point.sampleId}
          onMouseEnter={() => onHover(point)}
          onMouseLeave={() => onHover(null)}
          className="flex items-center justify-between gap-3 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-3 py-2 text-xs hover:border-[var(--line-strong)] hover:bg-[var(--paper)]"
        >
          <span className="min-w-0">
            <span className="mr-2 text-[var(--faint)]">#{index + 1}</span>
            <span className="font-medium text-[var(--ink)]">{point.sampleLabel}</span>
            <span className="ml-2 text-[var(--muted)]">{point.status}</span>
          </span>
          <span className="shrink-0 font-mono text-[var(--ink)]">{formatRunMetricValue(descriptor, point.metrics[metricKey])}</span>
        </Link>
      ))}
    </div>
  );
}

function StripPlot({
  points,
  metricKey,
  runHrefBase,
  onHover,
}: {
  points: RunMetricPoint[];
  metricKey: RunMetricKey;
  runHrefBase: string;
  onHover: (point: RunMetricPoint | null) => void;
}) {
  const descriptor = metricDescriptor(metricKey);
  const values = points.map((point) => point.metrics[metricKey].value ?? 0);
  const [min, max] = extent(values);

  return (
    <div className="relative h-28 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] px-7 py-8">
      <div className="absolute left-7 right-7 top-1/2 h-px bg-[var(--line-strong)]" />
      {points.map((point, index) => {
        const value = point.metrics[metricKey].value ?? 0;
        const left = scale(value, min, max, CHART_PAD, CHART_WIDTH - CHART_PAD);
        return (
          <Link
            href={runHref(runHrefBase, point.sampleId)}
            key={point.sampleId}
            onMouseEnter={() => onHover(point)}
            onMouseLeave={() => onHover(null)}
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[var(--card)] bg-[var(--accent)] shadow-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            style={{ left: `${(left / CHART_WIDTH) * 100}%`, transform: `translate(-50%, calc(-50% + ${index % 3 - 1}px))` }}
            title={`${point.sampleLabel}: ${formatRunMetricValue(descriptor, point.metrics[metricKey])}`}
          />
        );
      })}
      <div className="absolute bottom-2 left-7 text-[10px] text-[var(--muted)]">{formatRunMetricValue(descriptor, min)}</div>
      <div className="absolute bottom-2 right-7 text-[10px] text-[var(--muted)]">{formatRunMetricValue(descriptor, max)}</div>
    </div>
  );
}

function Histogram({
  points,
  metricKey,
  runHrefBase,
  onHover,
}: {
  points: RunMetricPoint[];
  metricKey: RunMetricKey;
  runHrefBase: string;
  onHover: (point: RunMetricPoint | null) => void;
}) {
  const descriptor = metricDescriptor(metricKey);
  const values = points.map((point) => point.metrics[metricKey].value ?? 0);
  const [min, max] = extent(values);
  const binCount = Math.min(8, Math.max(4, Math.ceil(Math.sqrt(points.length))));
  const bins = Array.from({ length: binCount }, (_, index) => ({
    index,
    points: [] as RunMetricPoint[],
  }));

  points.forEach((point) => {
    const value = point.metrics[metricKey].value ?? 0;
    const binIndex = Math.min(binCount - 1, Math.floor(((value - min) / (max - min)) * binCount));
    bins[binIndex]?.points.push(point);
  });

  const maxBin = Math.max(...bins.map((bin) => bin.points.length), 1);
  const p50 = percentile(values, 0.5);
  const p95 = percentile(values, 0.95);

  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] p-4">
      <div className="flex h-36 items-end gap-1">
        {bins.map((bin) => (
          <div
            key={bin.index}
            onMouseEnter={() => onHover(bin.points[0] ?? null)}
            onMouseLeave={() => onHover(null)}
            className="flex-1 rounded-t-sm bg-[var(--accent-soft)] ring-1 ring-inset ring-[var(--line)]"
            style={{ height: `${Math.max(8, (bin.points.length / maxBin) * 100)}%` }}
            title={`${bin.points.length} runs`}
          />
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between text-[10px] text-[var(--muted)]">
        <span>{formatRunMetricValue(descriptor, min)}</span>
        <span>p50 {formatRunMetricValue(descriptor, p50)} · p95 {formatRunMetricValue(descriptor, p95)}</span>
        <span>{formatRunMetricValue(descriptor, max)}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {points.slice(0, 12).map((point) => (
          <Link
            href={runHref(runHrefBase, point.sampleId)}
            key={point.sampleId}
            onMouseEnter={() => onHover(point)}
            onMouseLeave={() => onHover(null)}
            className="rounded-full border border-[var(--line)] bg-[var(--card)] px-2 py-0.5 font-mono text-[10px] text-[var(--muted)] hover:border-[var(--line-strong)] hover:text-[var(--ink)]"
          >
            {point.runName}
          </Link>
        ))}
      </div>
    </div>
  );
}

function ScatterPlot({
  points,
  primaryMetricKey,
  secondaryMetricKey,
  runHrefBase,
  onHover,
}: {
  points: RunMetricPoint[];
  primaryMetricKey: RunMetricKey;
  secondaryMetricKey: RunMetricKey;
  runHrefBase: string;
  onHover: (point: RunMetricPoint | null) => void;
}) {
  const xDescriptor = metricDescriptor(primaryMetricKey);
  const yDescriptor = metricDescriptor(secondaryMetricKey);
  const xValues = points.map((point) => point.metrics[primaryMetricKey].value ?? 0);
  const yValues = points.map((point) => point.metrics[secondaryMetricKey].value ?? 0);
  const [xMin, xMax] = extent(xValues);
  const [yMin, yMax] = extent(yValues);

  return (
    <div>
      {points.length < 10 ? (
        <div className="mb-3 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-xs text-[var(--muted)]">
          Too few points for trend. Showing comparable runs only.
        </div>
      ) : null}
      <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="h-72 w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)]">
        <line x1={CHART_PAD} y1={CHART_HEIGHT - CHART_PAD} x2={CHART_WIDTH - CHART_PAD} y2={CHART_HEIGHT - CHART_PAD} stroke="var(--line-strong)" />
        <line x1={CHART_PAD} y1={CHART_PAD} x2={CHART_PAD} y2={CHART_HEIGHT - CHART_PAD} stroke="var(--line-strong)" />
        {points.map((point) => {
          const x = scale(point.metrics[primaryMetricKey].value ?? 0, xMin, xMax, CHART_PAD, CHART_WIDTH - CHART_PAD);
          const y = scale(point.metrics[secondaryMetricKey].value ?? 0, yMin, yMax, CHART_HEIGHT - CHART_PAD, CHART_PAD);
          return (
            <a
              href={runHref(runHrefBase, point.sampleId)}
              key={point.sampleId}
              onMouseEnter={() => onHover(point)}
              onMouseLeave={() => onHover(null)}
            >
              <circle cx={x} cy={y} r="5" fill="var(--accent)" stroke="var(--card)" strokeWidth="2">
                <title>{`${point.sampleLabel}: ${xDescriptor.label} ${formatRunMetricValue(xDescriptor, point.metrics[primaryMetricKey])}, ${yDescriptor.label} ${formatRunMetricValue(yDescriptor, point.metrics[secondaryMetricKey])}`}</title>
              </circle>
            </a>
          );
        })}
        <text x={CHART_WIDTH / 2} y={CHART_HEIGHT - 6} textAnchor="middle" fontSize="11" fill="var(--muted)">{xDescriptor.label}</text>
        <text x="10" y={CHART_HEIGHT / 2} textAnchor="middle" fontSize="11" fill="var(--muted)" transform={`rotate(-90 10 ${CHART_HEIGHT / 2})`}>{yDescriptor.label}</text>
      </svg>
    </div>
  );
}

export function SampleRunMetricExplorer({
  points,
  runHrefBase = "/samples",
  initialMode = "1d",
  initialPrimaryMetric = "score",
  initialSecondaryMetric = "duration_ms",
}: SampleRunMetricExplorerProps) {
  const [mode, setMode] = useState<SampleRunMetricExplorerMode>(initialMode);
  const [primaryMetricKey, setPrimaryMetricKey] = useState<RunMetricKey>(initialPrimaryMetric);
  const [secondaryMetricKey, setSecondaryMetricKey] = useState<RunMetricKey>(initialSecondaryMetric);
  const [hoveredPoint, setHoveredPoint] = useState<RunMetricPoint | null>(null);
  const comparablePoints = useMemo(
    () => availableMetricPoints(points, primaryMetricKey, mode === "2d" ? secondaryMetricKey : undefined),
    [mode, points, primaryMetricKey, secondaryMetricKey],
  );
  const view = selectSampleRunMetricExplorerView(mode, points, primaryMetricKey, secondaryMetricKey);
  const primaryDescriptor = metricDescriptor(primaryMetricKey);

  return (
    <section className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card" data-testid="sample-metric-explorer">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--ink)]">Run metric explorer</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Compare normalized run metrics. Cost and token metrics appear only when observed instrumentation is present.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] p-0.5 text-xs">
            <button type="button" onClick={() => setMode("1d")} className={`rounded px-2 py-1 ${mode === "1d" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--muted)]"}`}>1D</button>
            <button type="button" onClick={() => setMode("2d")} className={`rounded px-2 py-1 ${mode === "2d" ? "bg-[var(--card)] text-[var(--ink)] shadow-sm" : "text-[var(--muted)]"}`}>2D</button>
          </div>
          <select value={primaryMetricKey} onChange={(event) => setPrimaryMetricKey(event.target.value as RunMetricKey)} className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-2 py-1 text-xs text-[var(--ink)]">
            {RUN_METRIC_DESCRIPTORS.map((descriptor) => (
              <option key={descriptor.key} value={descriptor.key}>{descriptor.label}</option>
            ))}
          </select>
          {mode === "2d" ? (
            <select value={secondaryMetricKey} onChange={(event) => setSecondaryMetricKey(event.target.value as RunMetricKey)} className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] px-2 py-1 text-xs text-[var(--ink)]">
              {RUN_METRIC_DESCRIPTORS.map((descriptor) => (
                <option key={descriptor.key} value={descriptor.key}>{descriptor.label}</option>
              ))}
            </select>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          {view === "empty" ? (
            <div className="rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] bg-[var(--paper)] px-4 py-10 text-center text-sm text-[var(--muted)]">
              {primaryDescriptor.unavailableLabel ?? "No numeric values are available for this metric."}
            </div>
          ) : null}
          {view === "too-few-points" ? (
            <div className="rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] bg-[var(--paper)] px-4 py-10 text-center text-sm text-[var(--muted)]">
              Need at least three runs with both selected metrics to draw a 2D comparison.
            </div>
          ) : null}
          {view === "ranked-list" ? (
            <RankedList points={comparablePoints} metricKey={primaryMetricKey} runHrefBase={runHrefBase} onHover={setHoveredPoint} />
          ) : null}
          {view === "strip" ? (
            <StripPlot points={comparablePoints} metricKey={primaryMetricKey} runHrefBase={runHrefBase} onHover={setHoveredPoint} />
          ) : null}
          {view === "histogram" ? (
            <Histogram points={comparablePoints} metricKey={primaryMetricKey} runHrefBase={runHrefBase} onHover={setHoveredPoint} />
          ) : null}
          {view === "scatter" ? (
            <ScatterPlot points={comparablePoints} primaryMetricKey={primaryMetricKey} secondaryMetricKey={secondaryMetricKey} runHrefBase={runHrefBase} onHover={setHoveredPoint} />
          ) : null}
        </div>
        <HoverCard point={hoveredPoint ?? comparablePoints[0] ?? null} primaryMetricKey={primaryMetricKey} secondaryMetricKey={secondaryMetricKey} />
      </div>
    </section>
  );
}
