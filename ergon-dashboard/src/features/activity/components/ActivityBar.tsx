"use client";

import type { ActivityStackItem, ActivityKind, RunActivity } from "@/features/activity/types";

const KIND_STYLES: Record<
  ActivityKind,
  { bar: string; marker: string; text: string; label: string }
> = {
  execution: {
    bar: "bg-indigo-600 border-indigo-700",
    marker: "bg-indigo-600",
    text: "text-indigo-900 dark:text-indigo-100",
    label: "Execution",
  },
  graph: {
    bar: "bg-sky-600 border-sky-700",
    marker: "bg-sky-600",
    text: "text-sky-900 dark:text-sky-100",
    label: "Graph",
  },
  message: {
    bar: "bg-amber-500 border-amber-600",
    marker: "bg-amber-500",
    text: "text-amber-900 dark:text-amber-100",
    label: "Talk",
  },
  artifact: {
    bar: "bg-lime-600 border-lime-700",
    marker: "bg-lime-600",
    text: "text-lime-900 dark:text-lime-100",
    label: "Artifact",
  },
  evaluation: {
    bar: "bg-fuchsia-600 border-fuchsia-700",
    marker: "bg-fuchsia-600",
    text: "text-fuchsia-900 dark:text-fuchsia-100",
    label: "Evaluation",
  },
  context: {
    bar: "bg-cyan-600 border-cyan-700",
    marker: "bg-cyan-600",
    text: "text-cyan-900 dark:text-cyan-100",
    label: "Context",
  },
  sandbox: {
    bar: "bg-slate-600 border-slate-700",
    marker: "bg-slate-600",
    text: "text-slate-900 dark:text-slate-100",
    label: "Sandbox",
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
      className={`absolute top-1 h-7 overflow-hidden rounded-md border text-left shadow-sm transition-all hover:z-20 hover:scale-[1.01] hover:shadow-md focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
        isMarker ? styles.marker : styles.bar
      } ${selected ? "z-30 ring-2 ring-indigo-500 ring-offset-1" : ""} ${
        highlighted ? "z-20 ring-2 ring-slate-900/40 dark:ring-white/50" : ""
      }`}
      style={{
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        minWidth: isMarker ? 8 : 36,
      }}
      title={`${styles.label}: ${activity.label}`}
      aria-label={`Open activity ${activity.label}`}
      data-testid={testIdFor(activity)}
      data-kind={activity.kind}
      data-task-id={activity.taskId ?? ""}
    >
      {isMarker ? (
        <span className="block h-full w-full" aria-hidden />
      ) : (
        <span className="block truncate px-2 py-1 text-[11px] font-semibold text-white">
          {activity.label}
        </span>
      )}
    </button>
  );
}
