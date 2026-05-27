"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { DAGCanvas } from "@/components/dag/DAGCanvas";
import { StatusBadge } from "@/components/common/StatusBadge";

import { SampleRuntimeSummaryHeader, type SampleHeaderMetricValues } from "@/components/sample/SampleRuntimeSummaryHeader";
import { UnifiedEventStream } from "@/components/sample/UnifiedEventStream";
import { TaskWorkspace } from "@/components/workspace/TaskWorkspace";
import { ActivityStackTimeline } from "@/features/activity/components/ActivityStackTimeline";
import { buildSampleActivities } from "@/features/activity/buildSampleActivities";
import { resolveActivitySnapshotSequence } from "@/features/activity/snapshotSequence";
import type { SampleActivity } from "@/features/activity/types";
import {
  parseGraphMutationDtoArray,
  type GraphMutationDto,
} from "@/features/graph/contracts/graphMutations";
import { useSampleWorkspaceState } from "@/hooks/useSampleWorkspaceState";
import { buildSampleEvents } from "@/lib/sampleEvents";
import { SampleLifecycleStatus, SerializedSampleWorkspaceState, TaskStatus, type SampleWorkspaceState } from "@/lib/types";
import {
  nearestMutationAtOrBefore,
  useSampleDisplayState,
} from "@/components/sample/useSampleDisplayState";
import { useSampleKeyboardShortcuts } from "@/components/sample/useSampleKeyboardShortcuts";
import { panelPercent, useSamplePanelLayout } from "@/components/sample/useSamplePanelLayout";
import { resolveReplayStep } from "@/components/sample/replayNavigation";
import { formatDuration } from "@/lib/sample-state/formatters";

type OptionalRunMetrics = {
  metrics?: {
    totalTokens?: number | null;
    totalCostUsd?: number | null;
    costObserved?: boolean | null;
  } | null;
};

function countObservedTokens(runState: SampleWorkspaceState | null): number | null {
  if (!runState) return null;
  let tokenCount = 0;
  for (const events of runState.contextEventsByTask.values()) {
    for (const event of events) {
      const payload = event.payload;
      if ("turn_token_ids" in payload && payload.turn_token_ids) {
        tokenCount += payload.turn_token_ids.length;
      }
    }
  }
  return tokenCount > 0 ? tokenCount : null;
}

export function SampleWorkspacePage({
  sampleId,
  initialRunState = null,
  ssrError = null,
}: {
  sampleId: string;
  initialRunState?: SerializedSampleWorkspaceState | null;
  ssrError?: string | null;
}) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null);
  const [isStreamOpen, setIsStreamOpen] = useState(false);
  const [isTimelineOpen, setIsTimelineOpen] = useState(true);
  const {
    verticalLayout,
    setVerticalLayout,
    horizontalLayout,
    setHorizontalLayout,
    hasLoadedPanelLayouts,
  } = useSamplePanelLayout();
  const { runState, isLoading, error, isSubscribed } = useSampleWorkspaceState(sampleId, initialRunState);

  const [mutations, setMutations] = useState<GraphMutationDto[]>([]);
  const requestedSequenceRef = useRef<number | null>(null);
  const pendingActivityResolutionRef = useRef<SampleActivity | null>(null);
  const selectedActivityIdRef = useRef<string | null>(null);
  const mutationsLoadedRef = useRef(false);

  const {
    displayState,
    selectedActivityId,
    setSelectedActivityId,
    snapshotSequence,
    setSnapshotSequence,
    currentSequence,
    selectedTimelineTime,
  } = useSampleDisplayState(runState, mutations);

  useEffect(() => {
    selectedActivityIdRef.current = selectedActivityId;
  }, [selectedActivityId]);

  // Fetch mutations once per run load so snapshot selection is always ready.
  useEffect(() => {
    let cancelled = false;
    mutationsLoadedRef.current = false;
    pendingActivityResolutionRef.current = null;
    fetch(`/api/samples/${sampleId}/mutations`)
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const parsed = parseGraphMutationDtoArray(data);
        mutationsLoadedRef.current = true;
        setMutations(parsed);
        const requestedSequence = requestedSequenceRef.current;
        requestedSequenceRef.current = null;
        if (requestedSequence !== null) {
          setSnapshotSequence(nearestMutationAtOrBefore(parsed, requestedSequence)?.sequence ?? null);
          return;
        }

        const pendingActivity = pendingActivityResolutionRef.current;
        pendingActivityResolutionRef.current = null;
        if (pendingActivity && selectedActivityIdRef.current === pendingActivity.id) {
          const sequence = resolveActivitySnapshotSequence(pendingActivity, parsed);
          const resolvedSequence =
            sequence === null
              ? null
              : (nearestMutationAtOrBefore(parsed, sequence)?.sequence ?? sequence);
          setSnapshotSequence(resolvedSequence);
        }
      })
      .catch(() => {
        if (cancelled) return;
        mutationsLoadedRef.current = true;
        pendingActivityResolutionRef.current = null;
        setMutations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sampleId, setSnapshotSequence]);

  // Status counts shown in the run header. Only leaf tasks so the totals
  // match the "units of work" the user is tracking (parents double-count).
  const { leafStatusCounts, leafTotal } = useMemo(() => {
    const empty: Record<TaskStatus, number> = {
      [TaskStatus.PENDING]: 0,
      [TaskStatus.READY]: 0,
      [TaskStatus.RUNNING]: 0,
      [TaskStatus.COMPLETED]: 0,
      [TaskStatus.FAILED]: 0,
      [TaskStatus.CANCELLED]: 0,
    };
    if (!displayState) return { leafStatusCounts: empty, leafTotal: 0 };
    let total = 0;
    for (const task of displayState.tasks.values()) {
      if (!task.isLeaf) continue;
      empty[task.status] = (empty[task.status] ?? 0) + 1;
      total += 1;
    }
    return { leafStatusCounts: empty, leafTotal: total };
  }, [displayState]);

  const runHeaderMetrics: SampleHeaderMetricValues = useMemo(() => {
    const optionalMetrics = runState as (SampleWorkspaceState & OptionalRunMetrics) | null;
    return {
      tasks: {
        completed: leafStatusCounts[TaskStatus.COMPLETED],
        running: leafStatusCounts[TaskStatus.RUNNING],
        failed: leafStatusCounts[TaskStatus.FAILED],
        total: leafTotal,
      },
      tokens: optionalMetrics?.metrics?.totalTokens ?? countObservedTokens(runState),
      costUsd: optionalMetrics?.metrics?.totalCostUsd ?? null,
      costObserved: optionalMetrics?.metrics?.costObserved ?? false,
      score: runState?.finalScore ?? null,
    };
  }, [leafStatusCounts, leafTotal, runState]);

  // D4: Unified event log for the replayed inspector view.
  const events = useMemo(() => buildSampleEvents(displayState), [displayState]);
  // Trace spans are an immutable map of the full run. Replay moves the cursor
  // over this map; it should not relayout or clip completed spans.
  const traceEvents = useMemo(() => buildSampleEvents(runState), [runState]);

  const activities = useMemo(
    () =>
      buildSampleActivities({
        runState,
        events: traceEvents,
        mutations,
        currentSequence: snapshotSequence,
      }),
    [runState, traceEvents, mutations, snapshotSequence],
  );

  const selectedActivity = useMemo(
    () => activities.find((activity) => activity.id === selectedActivityId) ?? null,
    [activities, selectedActivityId],
  );

  const clearReplaySelection = () => {
    requestedSequenceRef.current = null;
    pendingActivityResolutionRef.current = null;
    selectedActivityIdRef.current = null;
    setSelectedActivityId(null);
    setSnapshotSequence(null);
  };

  const highlightedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    if (selectedTaskId) ids.add(selectedTaskId);
    if (selectedActivity?.taskId) ids.add(selectedActivity.taskId);
    return ids;
  }, [selectedActivity, selectedTaskId]);

  useSampleKeyboardShortcuts({
    selectedTaskId,
    clearSelectedTask: () => setSelectedTaskId(null),
    snapshotSequence,
    setSnapshotSequence: (sequence) => {
      if (sequence === null) {
        clearReplaySelection();
        return;
      }
      setSnapshotSequence(sequence);
    },
    statusFilter,
    setStatusFilter,
    toggleEventStream: () => setIsStreamOpen((prev) => !prev),
    mutations,
  });

  useEffect(() => {
    if (!selectedTaskId || !displayState) return;
    if (!displayState.tasks.has(selectedTaskId)) {
      setSelectedTaskId(null);
      setSelectionNotice("The selected task disappeared from the latest run topology, so the inspector was reset.");
    }
  }, [displayState, selectedTaskId]);

  const status = runState?.status ?? "pending";
  const experimentHref = runState?.definitionId ? `/experiments/${runState.definitionId}` : "/experiments";
  const isInspectorOpen = selectedTaskId !== null;

  const handleTaskClick = (taskId: string) => {
    setSelectionNotice(null);
    pendingActivityResolutionRef.current = null;
    selectedActivityIdRef.current = null;
    setSelectedActivityId(null);
    setSelectedTaskId((prev) => (prev === taskId ? null : taskId));
  };

  const handleSequenceChange = (sequence: number) => {
    pendingActivityResolutionRef.current = null;
    const mutation = nearestMutationAtOrBefore(mutations, sequence);
    setSnapshotSequence(mutation?.sequence ?? sequence);
  };

  const handleActivityClick = (activity: SampleActivity) => {
    setSelectionNotice(null);
    requestedSequenceRef.current = null;
    selectedActivityIdRef.current = activity.id;
    setSelectedActivityId(activity.id);
    const sequence = resolveActivitySnapshotSequence(activity, mutations);
    if (sequence !== null) {
      handleSequenceChange(sequence);
    } else {
      setSnapshotSequence(null);
      pendingActivityResolutionRef.current = mutationsLoadedRef.current ? null : activity;
    }
    if (activity.taskId) {
      setSelectedTaskId(activity.taskId);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--paper)] text-[var(--ink)]">
      {/* Run header strip */}
      <header
        className="flex items-center justify-between gap-5 border-b border-[var(--line)] bg-[var(--card)] px-8 py-3 shadow-card"
        data-testid="sample-header"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-1 text-xs text-[var(--muted)]">
            <Link href="/experiments" className="hover:text-[var(--ink)]">Experiments</Link>
            <span>›</span>
            <Link href={experimentHref} className="hover:text-[var(--ink)]">Experiment</Link>
            <span>›</span>
            <span className="font-mono text-[var(--ink)]">{sampleId.slice(0, 8)}…</span>
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <h1 className="max-w-[340px] truncate font-mono text-xl font-semibold tracking-[-0.02em]">
              {runState?.name ?? sampleId}
            </h1>
            <StatusBadge status={status as SampleLifecycleStatus} />
            <span className="rounded bg-[var(--paper-2)] px-2 py-0.5 font-mono text-xs text-[var(--muted)]">
              {snapshotSequence === null ? "live" : `snapshot · seq ${snapshotSequence}`} · {formatDuration(runState?.durationSeconds ?? null).value}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <SampleRuntimeSummaryHeader metrics={runHeaderMetrics} />

          {mutations.length > 0 && (
            <div
              className="flex items-center overflow-hidden rounded-[7px] border border-[var(--line)] bg-[var(--card)]"
              data-testid="replay-header-controls"
            >
              <button
                type="button"
                onClick={() => {
                  const sequence = resolveReplayStep(mutations, snapshotSequence, "previous");
                  if (sequence !== null) setSnapshotSequence(sequence);
                }}
                className="border-r border-[var(--line)] px-2 py-1 font-mono text-xs text-[var(--muted)] hover:bg-[var(--paper-2)] hover:text-[var(--ink)]"
                title="Previous graph snapshot"
                data-testid="replay-step-previous"
              >
                ←
              </button>
              <span className="min-w-20 px-2 py-1 text-center font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
                {snapshotSequence === null ? "live" : `seq ${snapshotSequence}`}
              </span>
              <button
                type="button"
                onClick={() => {
                  const sequence = resolveReplayStep(mutations, snapshotSequence, "next");
                  if (sequence !== null) setSnapshotSequence(sequence);
                }}
                className="border-l border-[var(--line)] px-2 py-1 font-mono text-xs text-[var(--muted)] hover:bg-[var(--paper-2)] hover:text-[var(--ink)]"
                title="Next graph snapshot"
                data-testid="replay-step-next"
              >
                →
              </button>
              {snapshotSequence !== null && (
                <button
                  type="button"
                  onClick={clearReplaySelection}
                  className="border-l border-[var(--line)] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--accent)] hover:bg-[var(--accent-soft)]"
                  title="Return graph to live mode"
                  data-testid="replay-return-live"
                >
                  live
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsStreamOpen((p) => !p)}
            aria-pressed={isStreamOpen}
            className={`rounded-[7px] px-2.5 py-1 text-xs font-medium transition-colors ${
              isStreamOpen
                ? "bg-[var(--ink)] text-[var(--paper)]"
                : "border border-[var(--line)] bg-[var(--card)] text-[var(--muted)] hover:bg-[var(--paper-2)]"
            }`}
            title="Toggle event stream (e)"
            data-testid="event-stream-toggle"
          >
            {isStreamOpen ? "Hide events" : "Event tracks"}
          </button>

          <button
            type="button"
            onClick={() => setIsTimelineOpen((p) => !p)}
            aria-pressed={isTimelineOpen}
            className={`rounded-[7px] px-2.5 py-1 text-xs font-medium transition-colors ${
              isTimelineOpen
                ? "bg-[var(--ink)] text-[var(--paper)]"
                : "border border-[var(--line)] bg-[var(--card)] text-[var(--muted)] hover:bg-[var(--paper-2)]"
            }`}
            title="Toggle activity timeline"
            data-testid="activity-timeline-toggle"
          >
            {isTimelineOpen ? "Hide timeline" : "Show timeline"}
          </button>

          <button
            type="button"
            disabled
            title="Re-run is not wired yet: no dashboard API endpoint exists for cloning or dispatching a run."
            data-testid="rerun-button"
            className="cursor-not-allowed rounded-[7px] border border-[var(--line)] bg-[var(--paper-2)] px-3 py-1 text-xs font-medium text-[var(--muted)] opacity-60"
          >
            Re-run unavailable
          </button>
          <button
            type="button"
            className="rounded-[7px] border-transparent bg-transparent px-2 py-1 text-xs text-[var(--muted)]"
          >
            ⋯
          </button>
        </div>
      </header>

      {ssrError && (
        <div
          className="mx-4 mt-2 rounded-[var(--radius-sm)] border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
          data-testid="ssr-error-banner"
        >
          <span className="mr-1.5 font-semibold">Server-side error:</span>
          {ssrError}
        </div>
      )}

      {error && !ssrError && (
        <div
          className="mx-4 mt-2 rounded-[var(--radius-sm)] border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
          data-testid="sample-staleness-banner"
        >
          {error}
        </div>
      )}

      <main className="relative min-h-0 flex-1 overflow-hidden">
        {selectionNotice && (
          <div
            className="absolute left-4 right-4 top-2 z-40 rounded-[var(--radius-sm)] border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
            data-testid="selection-reset-notice"
          >
            {selectionNotice}
          </div>
        )}
        <Group
          key={`${hasLoadedPanelLayouts ? "hydrated" : "initial"}-${
            isTimelineOpen && activities.length > 0 ? "with-timeline" : "without-timeline"
          }`}
          orientation="vertical"
          defaultLayout={
            isTimelineOpen && activities.length > 0
              ? verticalLayout
              : { "graph-workspace": 100 }
          }
          onLayoutChange={(layout) => {
            if (isTimelineOpen && activities.length > 0) {
              setVerticalLayout(layout);
            }
          }}
          className="size-full"
        >
          <Panel
            id="graph-workspace"
            defaultSize={
              isTimelineOpen && activities.length > 0
                ? panelPercent(verticalLayout, "graph-workspace", 62)
                : "100%"
            }
            minSize="28%"
          >
            <Group
              key={`${hasLoadedPanelLayouts ? "hydrated" : "initial"}-${
                isInspectorOpen ? "with-workspace" : "without-workspace"
              }`}
              orientation="horizontal"
              defaultLayout={isInspectorOpen ? horizontalLayout : { graph: 100 }}
              onLayoutChange={(layout) => {
                if (isInspectorOpen) {
                  setHorizontalLayout(layout);
                }
              }}
              className="size-full"
            >
              <Panel
                id="graph"
                defaultSize={
                  isInspectorOpen
                    ? panelPercent(horizontalLayout, "graph", 58)
                    : "100%"
                }
                minSize="28%"
              >
                <section
                  className="relative h-full min-h-0 overflow-hidden"
                  data-testid="graph-region"
                >
                  <DAGCanvas
                    sampleId={sampleId}
                    runState={displayState}
                    isLoading={isLoading}
                    error={error}
                    isSubscribed={isSubscribed}
                    onTaskClick={handleTaskClick}
                    selectedTaskId={selectedTaskId}
                    highlightedTaskIds={highlightedTaskIds}
                  />

                  {isStreamOpen && events.length > 0 && (
                    <section
                      className="absolute bottom-4 left-4 z-20 max-h-[44vh] w-[520px] overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-pop"
                      data-testid="event-stream-region"
                    >
                      <UnifiedEventStream
                        events={events}
                        anchor={runState?.startedAt ?? null}
                        highlightedTaskId={selectedTaskId}
                        onTaskClick={(id) => {
                          setSelectionNotice(null);
                          setSelectedTaskId(id);
                        }}
                        onSequenceClick={(seq) => {
                          requestedSequenceRef.current = seq;
                          handleSequenceChange(seq);
                        }}
                      />
                    </section>
                  )}

                </section>
              </Panel>

              {isInspectorOpen && (
                <>
                  <Separator
                    id="workspace-resize-handle"
                    data-testid="workspace-resize-handle"
                    className="group relative z-30 w-3 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-[var(--accent-soft)] data-[separator=drag]:bg-[var(--accent-soft)]"
                    aria-label="Resize task workspace"
                  >
                    <div className="mx-auto h-full w-px bg-[var(--line)] transition-colors group-hover:bg-[var(--accent)]" />
                  </Separator>
                  <Panel
                    id="workspace"
                    defaultSize={panelPercent(horizontalLayout, "workspace", 42)}
                    minSize="24%"
                    maxSize="70%"
                  >
                    <section
                      className="h-full overflow-hidden rounded-l-[var(--radius)] border-l border-[var(--line)] bg-[var(--card)] shadow-pop"
                      data-testid="workspace-region"
                    >
                      <TaskWorkspace
                        runState={displayState}
                        taskId={selectedTaskId}
                        error={error}
                        onClearSelection={() => setSelectedTaskId(null)}
                        onJumpToSequence={(seq) => {
                          requestedSequenceRef.current = seq;
                          handleSequenceChange(seq);
                        }}
                        selectedTime={selectedTimelineTime}
                        selectedSequence={snapshotSequence}
                        selectedActivity={selectedActivity}
                      />
                    </section>
                  </Panel>
                </>
              )}
            </Group>
          </Panel>

          {isTimelineOpen && activities.length > 0 && (
            <>
              <Separator
                id="timeline-resize-handle"
                data-testid="timeline-resize-handle"
                className="group relative z-30 h-3 shrink-0 cursor-row-resize bg-transparent transition-colors hover:bg-[var(--accent-soft)] data-[separator=drag]:bg-[var(--accent-soft)]"
                aria-label="Resize trace timeline"
              >
                <div className="my-auto h-px w-full bg-[var(--line)] transition-colors group-hover:bg-[var(--accent)]" />
              </Separator>
              <Panel
                id="timeline"
                defaultSize={panelPercent(verticalLayout, "timeline", 38)}
                minSize="18%"
                maxSize="70%"
              >
                <section
                  className="h-full overflow-auto border-t border-[var(--line)] bg-[var(--card)]"
                  data-testid="timeline-region"
                >
                  <ActivityStackTimeline
                    activities={activities}
                    mutations={mutations}
                    currentSequence={currentSequence}
                    selectedTaskId={selectedTaskId}
                    selectedActivityId={selectedActivityId}
                    onActivityClick={handleActivityClick}
                    onReturnToLive={clearReplaySelection}
                  />
                </section>
              </Panel>
            </>
          )}
        </Group>
      </main>
    </div>
  );
}
