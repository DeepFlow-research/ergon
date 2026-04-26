"use client";

import type { ActivityStackItem, ActivityKind, RunActivity } from "@/features/activity/types";

const KIND_STYLES: Record<
  ActivityKind,
  { fill: string; text: string; label: string; legendLabel: string }
> = {
  graph: {
    fill: "oklch(0.78 0.14 305)",
    text: "white",
    label: "Graph mutation",
    legendLabel: "graph mutation",
  },
  execution: {
    fill: "oklch(0.74 0.16 295)",
    text: "white",
    label: "Execution",
    legendLabel: "task",
  },
  message: {
    fill: "oklch(0.74 0.14 70)",
    text: "white",
    label: "Message",
    legendLabel: "message",
  },
  artifact: {
    fill: "oklch(0.72 0.16 145)",
    text: "white",
    label: "Artifact",
    legendLabel: "artifact",
  },
  evaluation: {
    fill: "oklch(0.68 0.18 345)",
    text: "white",
    label: "Evaluation",
    legendLabel: "evaluation",
  },
  context: {
    fill: "oklch(0.66 0.12 230)",
    text: "white",
    label: "Context",
    legendLabel: "context/tool",
  },
  sandbox: {
    fill: "oklch(0.70 0.12 195)",
    text: "white",
    label: "Sandbox",
    legendLabel: "sandbox",
  },
};

export function activityKindLabel(kind: ActivityKind): string {
  return KIND_STYLES[kind].label;
}

export function activityKindLegendLabel(kind: ActivityKind): string {
  return KIND_STYLES[kind].legendLabel;
}

export function activityKindColor(kind: ActivityKind): string {
  return KIND_STYLES[kind].fill;
}

export const ALL_ACTIVITY_KINDS = Object.keys(KIND_STYLES) as ActivityKind[];

function testIdFor(activity: RunActivity): string {
  return `activity-bar-${activity.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function ActivityBar({
  item,
  selected,
  highlighted,
  current,
  relation,
  onClick,
  onHoverStart,
  onHoverEnd,
}: {
  item: ActivityStackItem;
  selected: boolean;
  highlighted: boolean;
  current: boolean;
  relation: "focused" | "related" | "dimmed" | "none";
  onClick: (activity: RunActivity) => void;
  onHoverStart: (activity: RunActivity) => void;
  onHoverEnd: () => void;
}) {
  const { activity, leftPct, widthPct } = item;
  const styles = KIND_STYLES[activity.kind];
  const isMarker = activity.isInstant;

  return (
    <button
      type="button"
      onClick={() => onClick(activity)}
      onMouseEnter={() => onHoverStart(activity)}
      onMouseLeave={onHoverEnd}
      onFocus={() => onHoverStart(activity)}
      onBlur={onHoverEnd}
      className={`absolute top-1 flex h-[25px] items-center overflow-visible rounded-full text-left transition-all hover:z-40 hover:brightness-110 focus:z-40 focus:outline-none focus:ring-2 focus:ring-white/40 ${
        selected ? "z-30 ring-2 ring-[var(--accent)] ring-offset-0" : ""
      } ${current ? "z-[25] shadow-[0_0_0_3px_oklch(0.92_0.15_95),0_0_0_5px_rgba(7,11,18,0.75)]" : ""} ${
        current && isMarker ? "scale-125" : ""
      } ${highlighted ? "z-20 ring-2 ring-white/45" : ""} ${
        relation === "dimmed" ? "opacity-25 grayscale" : ""
      } ${relation === "focused" ? "z-30 ring-2 ring-[var(--accent)]" : ""} ${
        relation === "related" ? "z-20 saturate-150" : ""
      }`}
      style={{
        left: `${leftPct}%`,
        width: `${widthPct}%`,
        minWidth: isMarker ? 11 : 44,
        backgroundColor: styles.fill,
        color: styles.text,
      }}
      title={`${styles.label}: ${activity.label}`}
      aria-label={`Open activity ${activity.label}`}
      data-testid={testIdFor(activity)}
      data-kind={activity.kind}
      data-activity-id={activity.id}
      data-task-id={activity.taskId ?? ""}
      data-row={item.row}
      data-left-pct={leftPct}
      data-width-pct={widthPct}
      data-relation={relation}
      data-current={current ? "true" : "false"}
    >
      {/* Start marker circle */}
      <span
        className="pointer-events-none absolute left-0 top-1/2 -ml-[5px] -mt-[5px] size-[10px] rounded-full shadow-[0_0_0_2px_#070b12]"
        style={{ backgroundColor: styles.fill }}
        aria-hidden
      />
      {isMarker ? null : (
        <span className="block truncate pl-3 pr-2 text-[11px] font-semibold">
          {activity.label}
        </span>
      )}
    </button>
  );
}
