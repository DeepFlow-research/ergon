"use client";

import { useMemo, useState } from "react";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import { ACTIVITY_BAND_ORDER, stackActivities } from "@/features/activity/stackLayout";
import type { ActivityBand, RunActivity } from "@/features/activity/types";
import { resolveCurrentActivityId } from "@/features/activity/currentActivity";
import { formatClockTime } from "@/lib/timeFormat";
import { ActivityBar, activityKindLegendLabel, activityKindColor } from "./ActivityBar";

interface ActivityStackTimelineProps {
  activities: RunActivity[];
  mutations: GraphMutationDto[];
  currentSequence: number;
  selectedTaskId: string | null;
  selectedActivityId: string | null;
  onActivityClick: (activity: RunActivity) => void;
}

const ROW_HEIGHT = 31;
const BAND_LABELS: Record<ActivityBand, { title: string; note: string }> = {
  work: {
    title: "Work spans",
    note: "Executions and sandbox lifetimes.",
  },
  graph: {
    title: "Graph changes",
    note: "Node and edge mutations.",
  },
  tools: {
    title: "Tools / context",
    note: "Tool calls, commands, observations.",
  },
  communication: {
    title: "Communication",
    note: "Messages and coordination.",
  },
  outputs: {
    title: "Outputs / evals",
    note: "Artifacts, scores, pass/fail.",
  },
};
const STACK_ACTIVITY_KINDS = [
  "execution",
  "graph",
  "context",
  "sandbox",
  "message",
  "artifact",
  "evaluation",
] as const;

function timePositionPct(timestamp: string, startMs: number, endMs: number): number | null {
  const ms = Date.parse(timestamp);
  if (!Number.isFinite(ms)) return null;
  const spanMs = Math.max(1, endMs - startMs);
  return Math.min(100, Math.max(0, ((ms - startMs) / spanMs) * 100));
}

function lineageValueMatches(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  return Boolean(a && b && a === b);
}

function areActivitiesRelated(a: RunActivity, b: RunActivity): boolean {
  if (a.id === b.id) return true;
  return (
    lineageValueMatches(a.lineage.taskExecutionId, b.lineage.taskExecutionId) ||
    lineageValueMatches(a.lineage.sandboxId, b.lineage.sandboxId) ||
    lineageValueMatches(a.lineage.threadId, b.lineage.threadId) ||
    lineageValueMatches(a.lineage.taskId, b.lineage.taskId)
  );
}

function debugPreview(activity: RunActivity): string {
  return JSON.stringify(
    {
      kind: activity.kind,
      band: activity.band,
      label: activity.label,
      source: activity.debug.source,
      lineage: activity.lineage,
      metadata: activity.metadata,
      payload: activity.debug.payload,
    },
    null,
    2,
  );
}

function ActivityLineageCard({
  activity,
  related,
}: {
  activity: RunActivity;
  related: RunActivity[];
}) {
  const relatedSummary = related
    .filter((candidate) => candidate.id !== activity.id)
    .slice(0, 6);

  return (
    <div
      className="absolute right-8 top-14 z-50 w-[360px] rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] p-3 text-left text-xs text-[var(--ink)] shadow-pop"
      data-testid="activity-debug-preview"
    >
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
        Lineage
      </div>
      <div className="font-semibold">
        {activity.kind}: {activity.label}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-[var(--muted)]">
        <span>Band: {activity.band}</span>
        <span>Source: {activity.debug.source}</span>
        <span>Task: {activity.lineage.taskId ?? "—"}</span>
        <span>Execution: {activity.lineage.taskExecutionId ?? "—"}</span>
        <span>Sandbox: {activity.lineage.sandboxId ?? "—"}</span>
        <span>Seq: {activity.sequence ?? "—"}</span>
      </div>
      {relatedSummary.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Related events
          </div>
          <ul className="space-y-1 text-[11px] text-[var(--muted)]">
            {relatedSummary.map((candidate) => (
              <li key={candidate.id} className="truncate">
                <span className="font-medium text-[var(--ink)]">{candidate.kind}</span>
                {" · "}
                {candidate.label}
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="mt-3 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] p-2">
        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
          Raw payload
        </summary>
        <code className="mt-2 block max-h-44 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-[var(--muted)]">
          {debugPreview(activity)}
        </code>
      </details>
    </div>
  );
}

export function ActivityStackTimeline({
  activities,
  mutations,
  currentSequence,
  selectedTaskId,
  selectedActivityId,
  onActivityClick,
}: ActivityStackTimelineProps) {
  const [hoveredActivityId, setHoveredActivityId] = useState<string | null>(null);
  const layout = useMemo(() => stackActivities(activities), [activities]);
  const maxSequence = mutations.length > 0 ? mutations[mutations.length - 1].sequence : 0;
  const minSequence = mutations.length > 0 ? mutations[0].sequence : 0;
  const currentMutation = mutations.find((mutation) => mutation.sequence === currentSequence);
  const hasMutations = mutations.length > 0;
  const isReplayLocked = currentSequence > 0;
  const snapshotLeftPct = currentMutation
    ? timePositionPct(currentMutation.created_at, layout.startMs, layout.endMs)
    : null;
  const currentActivityId = resolveCurrentActivityId(
    activities,
    currentMutation?.created_at ?? null,
    currentMutation?.sequence ?? null,
  );

  if (activities.length === 0) {
    return (
      <div
        className="flex h-full items-center justify-center bg-[var(--paper)] text-sm text-[var(--muted)]"
        data-testid="activity-stack-region"
      >
        No activity has been recorded for this run yet.
      </div>
    );
  }

  const timeSlots = 8;
  const timeRange = layout.endMs - layout.startMs;
  const timeLabels = Array.from({ length: timeSlots }, (_, i) => {
    const ms = layout.startMs + (timeRange / (timeSlots - 1)) * i;
    return formatClockTime(ms);
  });
  const focusActivity =
    activities.find((activity) => activity.id === hoveredActivityId) ??
    activities.find((activity) => activity.id === selectedActivityId) ??
    null;
  const relatedActivities = focusActivity
    ? activities.filter((activity) => areActivitiesRelated(focusActivity, activity))
    : [];
  const relatedActivityIds = new Set(relatedActivities.map((activity) => activity.id));

  return (
    <div className="relative h-full bg-[var(--paper-2)] text-[var(--ink)]" data-testid="activity-stack-region">
      {/* Header bar */}
      <div className="flex h-11 items-center justify-between overflow-hidden border-b border-[var(--line)] bg-[var(--card)] px-6">
        <div className="flex items-center gap-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--faint)]">
            Concurrent execution{" "}
            <span className="ml-1.5 font-normal normal-case tracking-normal text-[var(--muted)]">
              bars are task attempts; dots are graph snapshots.
            </span>
          </div>

          {!isReplayLocked && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              <span className="size-1.5 animate-status-pulse rounded-full bg-emerald-500" />
              Live · auto-tail
            </span>
          )}

          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]" data-testid="activity-current-sequence">
            seq {minSequence} — {maxSequence || currentMutation?.sequence || currentSequence} · {isReplayLocked ? "replay" : "streaming"}
          </span>

          {isReplayLocked && (
            <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--accent)]" data-testid="snapshot-lock-label">
              graph locked · seq {currentSequence}
            </span>
          )}

        </div>

        {/* Kind legend */}
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-[11px] text-[var(--muted)]" data-testid="activity-kind-legend">
          <span className="flex items-center gap-1.5 font-medium text-[var(--ink)]">
            <span className="inline-block h-[7px] w-[18px] rounded-full bg-[var(--accent-soft)] ring-1 ring-[var(--line)]" />
            Span
          </span>
          <span className="flex items-center gap-1.5 font-medium text-[var(--ink)]">
            <span className="inline-block size-[7px] rounded-full bg-[var(--accent)]" />
            Point event
          </span>
          {STACK_ACTIVITY_KINDS.map((kind) => (
            <span key={kind} className="flex items-center gap-1.5">
              <span className="inline-block size-[6px] rounded-full" style={{ backgroundColor: activityKindColor(kind) }} />
              {activityKindLegendLabel(kind)}
            </span>
          ))}
        </div>
      </div>

      {focusActivity && (
        <ActivityLineageCard activity={focusActivity} related={relatedActivities} />
      )}

      {/* Stack content */}
      <div className="relative px-6 pb-2 pt-3">
        <div className="grid" style={{ gridTemplateColumns: "140px 1fr", gap: "16px" }}>
          <div className="text-[11px] leading-[1.45] text-[var(--muted)]">
            <div className="font-semibold text-[var(--ink)]">Trace spans</div>
            Band = semantic category. Sub-row = visual overlap.
          </div>

          <div className="mb-1 grid min-w-0 font-mono text-[10px] text-[var(--faint)]" style={{ gridTemplateColumns: `repeat(${timeSlots}, 1fr)` }}>
              {timeLabels.map((label, i) => (
                <span key={i}>
                  {label}
                  {i === timeSlots - 2 && !isReplayLocked && <span className="ml-1 text-emerald-600">· now</span>}
                </span>
              ))}
          </div>
        </div>

        <div className="overflow-visible rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)]">
          {ACTIVITY_BAND_ORDER.map((band) => {
            const bandLayout = layout.bands.find((entry) => entry.band === band);
            if (!bandLayout) return null;
            const bandItems = layout.items.filter((item) => item.activity.band === band);
            const labels = BAND_LABELS[band];
            return (
              <div
                key={band}
                className="grid border-b border-[var(--line)] last:border-b-0"
                style={{ gridTemplateColumns: "140px 1fr" }}
                data-testid={`activity-band-${band}`}
              >
                <div className="border-r border-[var(--line)] bg-[var(--paper)] p-3 text-[11px] leading-[1.35] text-[var(--muted)]">
                  <div className="font-semibold uppercase tracking-[0.08em] text-[var(--ink)]">
                    {labels.title}
                  </div>
                  <div className="mt-1">{labels.note}</div>
                </div>
                <div
                  className="relative min-w-0"
                  style={{
                    height: Math.max(1, bandLayout.rowCount) * ROW_HEIGHT + 12,
                    backgroundImage:
                      "linear-gradient(to right, transparent calc(12.5% - 1px), var(--line) calc(12.5% - 1px), var(--line) 12.5%, transparent 12.5%)",
                    backgroundSize: "12.5% 100%",
                  }}
                >
                  {Array.from({ length: bandLayout.rowCount }).map((_, row) => (
                    <div
                      key={row}
                      className="absolute left-0 right-0 border-t border-dashed border-[var(--line)]"
                      style={{ top: 4 + row * ROW_HEIGHT + 25 + 3 }}
                      data-testid="activity-stack-row"
                    />
                  ))}

                  {bandItems.map((item) => {
                    const relation = !focusActivity
                      ? "none"
                      : item.activity.id === focusActivity.id
                        ? "focused"
                        : relatedActivityIds.has(item.activity.id)
                          ? "related"
                          : "dimmed";
                    return (
                      <div
                        key={item.activity.id}
                        className="absolute left-0 right-0"
                        style={{ top: 4 + item.row * ROW_HEIGHT }}
                      >
                        <ActivityBar
                          item={item}
                          selected={item.activity.id === selectedActivityId}
                          highlighted={Boolean(selectedTaskId && item.activity.taskId === selectedTaskId)}
                          current={item.activity.id === currentActivityId}
                          relation={relation}
                          onClick={onActivityClick}
                          onHoverStart={(activity) => setHoveredActivityId(activity.id)}
                          onHoverEnd={() => setHoveredActivityId(null)}
                        />
                      </div>
                    );
                  })}

            {/* Snapshot pin (indigo) */}
            {hasMutations && isReplayLocked && snapshotLeftPct !== null && (
              <>
                <div
                  className="absolute bottom-0 top-0 w-0.5 bg-[var(--accent)]"
                  style={{ left: `${snapshotLeftPct}%` }}
                  data-testid="snapshot-pin"
                />
                <div
                  className="absolute -top-5 -translate-x-1/2 rounded bg-[var(--accent)] px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-[0.04em] text-white"
                  style={{ left: `${snapshotLeftPct}%` }}
                >
                  SEQ {currentSequence}
                </div>
              </>
            )}

            {/* NOW cursor (green, live mode) */}
            {!isReplayLocked && (
              <>
                <div
                  className="absolute bottom-0 top-0 w-0.5 animate-status-pulse bg-emerald-500"
                  style={{ left: "85%" }}
                  data-testid="now-cursor"
                />
                <div
                  className="absolute -top-5 flex -translate-x-1/2 items-center gap-1 rounded bg-emerald-600 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-[0.04em] text-white"
                  style={{ left: "85%" }}
                  data-testid="now-cursor-pill"
                >
                  <span className="size-[5px] animate-status-pulse rounded-full bg-white" />
                  NOW
                </div>
              </>
            )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer hints */}
        <div className="mt-2 flex flex-wrap gap-4 text-[10px] text-[var(--faint)]" data-testid="activity-footer-hints">
          <span>{layout.rowCount} trace rows across {layout.bands.length} semantic bands</span>
          <span>Hover = lineage focus</span>
          <span>Click = inspect graph snapshot</span>
        </div>
      </div>
    </div>
  );
}
