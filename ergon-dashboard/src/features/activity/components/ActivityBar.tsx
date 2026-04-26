"use client";

import type { ActivityStackItem, ActivityKind, RunActivity } from "@/features/activity/types";

const KIND_STYLES: Record<
  ActivityKind,
  { bar: string; marker: string; text: string; label: string; fill: string; stroke: string }
> = {
  execution: {
    bar: "bg-amber-400 border-amber-300 text-[#2a1800]",
    marker: "bg-amber-400 text-amber-400",
    text: "text-[#2a1800]",
    label: "Execution",
    fill: "#fbbf24",
    stroke: "#fde68a",
  },
  graph: {
    bar: "bg-violet-400 border-violet-300 text-[#160b2f]",
    marker: "bg-violet-400 text-violet-400",
    text: "text-[#160b2f]",
    label: "Graph",
    fill: "#a78bfa",
    stroke: "#ddd6fe",
  },
  message: {
    bar: "bg-cyan-400 border-cyan-300 text-[#06242a]",
    marker: "bg-cyan-400 text-cyan-400",
    text: "text-[#06242a]",
    label: "Talk",
    fill: "#22d3ee",
    stroke: "#a5f3fc",
  },
  artifact: {
    bar: "bg-emerald-400 border-emerald-300 text-[#052e1d]",
    marker: "bg-emerald-400 text-emerald-400",
    text: "text-[#052e1d]",
    label: "Artifact",
    fill: "#34d399",
    stroke: "#a7f3d0",
  },
  evaluation: {
    bar: "bg-rose-400 border-rose-300 text-[#3a0610]",
    marker: "bg-rose-400 text-rose-400",
    text: "text-[#3a0610]",
    label: "Evaluation",
    fill: "#fb7185",
    stroke: "#fecdd3",
  },
  context: {
    bar: "bg-cyan-300 border-cyan-200 text-[#06242a]",
    marker: "bg-cyan-300 text-cyan-300",
    text: "text-[#06242a]",
    label: "Context",
    fill: "#67e8f9",
    stroke: "#cffafe",
  },
  sandbox: {
    bar: "bg-slate-500 border-slate-400 text-white",
    marker: "bg-slate-500 text-slate-500",
    text: "text-white",
    label: "Sandbox",
    fill: "#94a3b8",
    stroke: "#cbd5e1",
  },
};

export function activityKindLabel(kind: ActivityKind): string {
  return KIND_STYLES[kind].label;
}

function testIdFor(activity: RunActivity): string {
  return `activity-bar-${activity.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function ActivityBar({
  item,
  selected,
  highlighted,
  onClick,
}: {
  item: ActivityStackItem;
  selected: boolean;
  highlighted: boolean;
  onClick: (activity: RunActivity) => void;
}) {
  const { activity, leftPct, widthPct } = item;
  const styles = KIND_STYLES[activity.kind];
  const isMarker = activity.isInstant;
  return (
    <button
      type="button"
      onClick={() => onClick(activity)}
      className={`absolute top-1 h-[25px] overflow-hidden rounded-full border text-left shadow-[0_8px_20px_rgb(0_0_0/0.24)] transition-all hover:z-20 hover:scale-[1.01] focus:outline-none focus:ring-2 focus:ring-white/40 ${
        isMarker ? styles.marker : styles.bar
      } ${selected ? "z-30 ring-2 ring-rose-400 ring-offset-0" : ""} ${
        highlighted ? "z-20 ring-2 ring-white/45" : ""
      }`}
      style={{
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        minWidth: isMarker ? 11 : 44,
        backgroundColor: styles.fill,
        borderColor: styles.stroke,
        color: styles.fill,
      }}
      title={`${styles.label}: ${activity.label}`}
      aria-label={`Open activity ${activity.label}`}
      data-testid={testIdFor(activity)}
      data-kind={activity.kind}
      data-task-id={activity.taskId ?? ""}
    >
      {isMarker ? (
        <span className="block h-[11px] w-[11px] rounded-full border-2 border-[#070b12] shadow-[0_0_0_2px_rgb(255_255_255/0.12),0_0_14px_currentColor]" aria-hidden />
      ) : (
        <span className={`block truncate px-3 py-[5px] text-[10px] font-black ${styles.text}`}>
          {activity.label}
        </span>
      )}
    </button>
  );
}
