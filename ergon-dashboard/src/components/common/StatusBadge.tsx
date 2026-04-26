"use client";

import { ExperimentCohortStatus, RunLifecycleStatus, TaskStatus } from "@/lib/types";

type StatusType = TaskStatus | RunLifecycleStatus | ExperimentCohortStatus;

interface StatusConfig {
  label: string;
  dot: string;
  solidBg: string;
  solidBorder: string;
  solidText: string;
  animate?: boolean;
}

const statusConfig: Record<string, StatusConfig> = {
  [TaskStatus.PENDING]: {
    label: "Pending",
    dot: "var(--status-pending)",
    solidBg: "var(--paper-2)",
    solidBorder: "var(--line)",
    solidText: "var(--muted)",
  },
  [TaskStatus.READY]: {
    label: "Ready",
    dot: "var(--status-ready)",
    solidBg: "oklch(0.97 0.03 240)",
    solidBorder: "oklch(0.86 0.08 240)",
    solidText: "oklch(0.40 0.12 240)",
  },
  [TaskStatus.RUNNING]: {
    label: "Running",
    dot: "var(--status-running)",
    solidBg: "oklch(0.96 0.04 80)",
    solidBorder: "oklch(0.85 0.10 80)",
    solidText: "oklch(0.42 0.12 65)",
    animate: true,
  },
  [TaskStatus.COMPLETED]: {
    label: "Completed",
    dot: "var(--status-completed)",
    solidBg: "oklch(0.96 0.04 155)",
    solidBorder: "oklch(0.85 0.10 155)",
    solidText: "oklch(0.40 0.12 155)",
  },
  [TaskStatus.FAILED]: {
    label: "Failed",
    dot: "var(--status-failed)",
    solidBg: "oklch(0.96 0.04 22)",
    solidBorder: "oklch(0.85 0.10 22)",
    solidText: "oklch(0.40 0.16 22)",
  },
  [TaskStatus.CANCELLED]: {
    label: "Cancelled",
    dot: "var(--status-cancelled)",
    solidBg: "var(--paper-2)",
    solidBorder: "var(--line)",
    solidText: "var(--muted)",
  },
  executing: {
    label: "Executing",
    dot: "var(--status-running)",
    solidBg: "oklch(0.96 0.04 80)",
    solidBorder: "oklch(0.85 0.10 80)",
    solidText: "oklch(0.42 0.12 65)",
    animate: true,
  },
  evaluating: {
    label: "Evaluating",
    dot: "oklch(0.74 0.16 295)",
    solidBg: "oklch(0.96 0.04 295)",
    solidBorder: "oklch(0.85 0.10 295)",
    solidText: "oklch(0.40 0.16 295)",
    animate: true,
  },
  active: {
    label: "Active",
    dot: "var(--status-ready)",
    solidBg: "oklch(0.97 0.03 240)",
    solidBorder: "oklch(0.86 0.08 240)",
    solidText: "oklch(0.40 0.12 240)",
  },
  archived: {
    label: "Archived",
    dot: "var(--status-cancelled)",
    solidBg: "var(--paper-2)",
    solidBorder: "var(--line)",
    solidText: "var(--muted)",
  },
};

const defaultConfig: StatusConfig = {
  label: "Unknown",
  dot: "var(--faint)",
  solidBg: "var(--paper-2)",
  solidBorder: "var(--line)",
  solidText: "var(--muted)",
};

interface StatusBadgeProps {
  status: StatusType;
  variant?: "outline" | "solid";
  size?: "sm" | "md";
  showLabel?: boolean;
}

export function StatusBadge({
  status,
  variant = "solid",
  size = "md",
  showLabel = true,
}: StatusBadgeProps) {
  const sizeClass = size === "sm" ? "text-[10px] px-1.5 py-px" : "text-[11px] px-2 py-0.5";
  const config = statusConfig[status] || defaultConfig;

  if (variant === "outline") {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--card)] font-medium tracking-[0.01em] text-[var(--ink-2)] ${sizeClass}`}>
        <span
          className={`inline-block size-1.5 rounded-full ${config.animate ? "animate-status-pulse" : ""}`}
          style={{ backgroundColor: config.dot }}
        />
        {showLabel && <span>{config.label}</span>}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium tracking-[0.01em] ${sizeClass}`}
      style={{
        backgroundColor: config.solidBg,
        borderColor: config.solidBorder,
        color: config.solidText,
      }}
      data-status={status}
    >
      <span
        className={`inline-block size-1.5 rounded-full ${config.animate ? "animate-status-pulse" : ""}`}
        style={{ backgroundColor: config.dot }}
      />
      {showLabel && <span>{config.label}</span>}
    </span>
  );
}

export function StatusDot({
  status,
  size = "md",
}: {
  status: StatusType;
  size?: "sm" | "md" | "lg";
}) {
  const config = statusConfig[status] || defaultConfig;
  const sizeClasses = { sm: "size-2", md: "size-3", lg: "size-4" };

  return (
    <span className="relative inline-flex">
      <span
        className={`rounded-full ${sizeClasses[size]}`}
        style={{ backgroundColor: config.dot }}
      />
      {config.animate && (
        <span
          className="absolute inline-flex size-full animate-ping rounded-full opacity-75"
          style={{ backgroundColor: config.dot }}
        />
      )}
    </span>
  );
}
