"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Group, Panel, Separator, type Layout } from "react-resizable-panels";

import { DAGCanvas } from "@/components/dag/DAGCanvas";
import { StatusBadge } from "@/components/common/StatusBadge";

import { UnifiedEventStream } from "@/components/run/UnifiedEventStream";
import { TaskWorkspace } from "@/components/workspace/TaskWorkspace";
import { ActivityStackTimeline } from "@/features/activity/components/ActivityStackTimeline";
import { buildRunActivities } from "@/features/activity/buildRunActivities";
import { resolveActivitySnapshotSequence } from "@/features/activity/snapshotSequence";
import type { RunActivity } from "@/features/activity/types";
import {
  parseGraphMutationDtoArray,
  type GraphMutationDto,
} from "@/features/graph/contracts/graphMutations";
import { createReplayInitialState, replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { useRunState } from "@/hooks/useRunState";
import { buildRunEvents } from "@/lib/runEvents";
import { RunLifecycleStatus, SerializedWorkflowRunState, TaskStatus } from "@/lib/types";

const VERTICAL_LAYOUT_STORAGE_KEY = "ergon-run-debugger-vertical-layout:v1";
const HORIZONTAL_LAYOUT_STORAGE_KEY = "ergon-run-debugger-horizontal-layout:v1";
const DEFAULT_VERTICAL_LAYOUT: Layout = { "graph-workspace": 62, timeline: 38 };
const DEFAULT_HORIZONTAL_LAYOUT: Layout = { graph: 58, workspace: 42 };

function loadPanelLayout(storageKey: string, fallback: Layout): Layout {
  if (typeof window === "undefined") return fallback;

  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Layout;
    return Object.fromEntries(
      Object.entries(fallback).map(([id, defaultSize]) => {
        const size = parsed[id];
        return [id, Number.isFinite(size) ? size : defaultSize];
      }),
    );
  } catch {
    return fallback;
  }
}

function savePanelLayout(storageKey: string, layout: Layout): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(layout));
  } catch {
    // Ignore storage failures; resizing should still work for the session.
  }
}

function panelPercent(layout: Layout, id: string, fallback: number): string {
  const size = layout[id];
  return `${Number.isFinite(size) ? size : fallback}%`;
}

function formatSeconds(value: number | null): string {
  if (value == null) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${(value / 60).toFixed(1)}m`;
}

function formatPercent(value: number | null): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function nearestMutationAtOrBefore(
  mutations: GraphMutationDto[],
  sequence: number,
): GraphMutationDto | null {
  let selected: GraphMutationDto | null = null;
  for (const mutation of mutations) {
    if (mutation.sequence > sequence) break;
    selected = mutation;
  }
  return selected ?? mutations[0] ?? null;
}

export function RunWorkspacePage({
  runId,
  cohortId,
  initialRunState = null,
  ssrError = null,
}: {
  runId: string;
  cohortId?: string;
  initialRunState?: SerializedWorkflowRunState | null;
  ssrError?: string | null;
}) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null);
  const [isStreamOpen, setIsStreamOpen] = useState(false);
  const [verticalLayout, setVerticalLayout] = useState<Layout>(() =>
    loadPanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, DEFAULT_VERTICAL_LAYOUT),
  );
  const [horizontalLayout, setHorizontalLayout] = useState<Layout>(() =>
    loadPanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, DEFAULT_HORIZONTAL_LAYOUT),
  );
  const [hasLoadedPanelLayouts, setHasLoadedPanelLayouts] = useState(false);
  const { runState, isLoading, error, isSubscribed } = useRunState(runId, initialRunState);

  // A null snapshot means the graph follows live state; a sequence replays
  // mutations to that point.
  const [snapshotSequence, setSnapshotSequence] = useState<number | null>(null);
  const currentSequence = snapshotSequence ?? 0;
  const [mutations, setMutations] = useState<GraphMutationDto[]>([]);
  const requestedSequenceRef = useRef<number | null>(null);
  const pendingActivityResolutionRef = useRef<RunActivity | null>(null);
  const selectedActivityIdRef = useRef<string | null>(null);
  const mutationsLoadedRef = useRef(false);

  useEffect(() => {
    selectedActivityIdRef.current = selectedActivityId;
  }, [selectedActivityId]);

  useEffect(() => {
    setVerticalLayout(loadPanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, DEFAULT_VERTICAL_LAYOUT));
    setHorizontalLayout(loadPanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, DEFAULT_HORIZONTAL_LAYOUT));
    setHasLoadedPanelLayouts(true);
  }, []);

  // Fetch mutations once per run load so snapshot selection is always ready.
  useEffect(() => {
    let cancelled = false;
    mutationsLoadedRef.current = false;
    pendingActivityResolutionRef.current = null;
    fetch(`/api/runs/${runId}/mutations`)
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
  }, [runId]);

  // Build display state: replay only for an explicit snapshot; otherwise live.
  const displayState = useMemo(() => {
    if (snapshotSequence === null || mutations.length === 0) return runState;
    if (!runState) return runState;
    const replayBaseState = createReplayInitialState(runState, mutations, snapshotSequence);
    return replayToSequence(
      mutations,
      snapshotSequence,
      replayBaseState,
    );
  }, [runState, mutations, snapshotSequence]);

  const selectedTask = useMemo(() => {
    if (!displayState || !selectedTaskId) return null;
    return displayState.tasks.get(selectedTaskId) ?? null;
  }, [displayState, selectedTaskId]);

  // Status counts shown in the run header. Only leaf tasks so the totals
  // match the "units of work" the user is tracking (parents double-count).
  const { leafStatusCounts } = useMemo(() => {
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

  // D4: Unified event log for the replayed inspector view.
  const events = useMemo(() => buildRunEvents(displayState), [displayState]);
  // Trace spans are an immutable map of the full run. Replay moves the cursor
  // over this map; it should not relayout or clip completed spans.
  const traceEvents = useMemo(() => buildRunEvents(runState), [runState]);

  const activities = useMemo(
    () =>
      buildRunActivities({
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

  const selectedTimelineTime = useMemo(() => {
    if (snapshotSequence === null) return null;
    return nearestMutationAtOrBefore(mutations, snapshotSequence)?.created_at ?? null;
  }, [mutations, snapshotSequence]);

  const highlightedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    if (selectedTaskId) ids.add(selectedTaskId);
    if (selectedActivity?.taskId) ids.add(selectedActivity.taskId);
    return ids;
  }, [selectedActivity, selectedTaskId]);

  // D7: keyboard shortcuts — Esc unwinds UI state, `e` toggles event stream,
  // `1-6` filters by lifecycle status.
  useEffect(() => {
    const STATUS_ORDER: TaskStatus[] = [
      TaskStatus.PENDING,
      TaskStatus.READY,
      TaskStatus.RUNNING,
      TaskStatus.COMPLETED,
      TaskStatus.FAILED,
      TaskStatus.CANCELLED,
    ];
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) {
          return;
        }
      }

      if (e.key === "Escape") {
        if (selectedTaskId) { setSelectedTaskId(null); return; }
        if (snapshotSequence !== null) { setSnapshotSequence(null); return; }
        if (statusFilter) { setStatusFilter(null); return; }
        return;
      }

      if (e.key === "e" || e.key === "E") {
        setIsStreamOpen((prev) => !prev);
        return;
      }

      if (e.key === "ArrowLeft" && snapshotSequence !== null) {
        const idx = mutations.findIndex((m) => m.sequence === snapshotSequence);
        if (idx > 0) setSnapshotSequence(mutations[idx - 1].sequence);
        return;
      }
      if (e.key === "ArrowRight" && snapshotSequence !== null) {
        const idx = mutations.findIndex((m) => m.sequence === snapshotSequence);
        if (idx >= 0 && idx < mutations.length - 1) setSnapshotSequence(mutations[idx + 1].sequence);
        return;
      }

      if ((e.key === "d" || e.key === "D") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (selectedTaskId) setSelectedTaskId(null);
        return;
      }

      const idx = Number(e.key) - 1;
      if (!Number.isNaN(idx) && idx >= 0 && idx < STATUS_ORDER.length) {
        const next = STATUS_ORDER[idx];
        setStatusFilter((prev) => (prev === next ? null : next));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedTaskId, statusFilter, mutations, snapshotSequence]);

  useEffect(() => {
    if (!selectedTaskId || !displayState) return;
    if (!displayState.tasks.has(selectedTaskId)) {
      setSelectedTaskId(null);
      setSelectionNotice("The selected task disappeared from the latest run topology, so the inspector was reset.");
    }
  }, [displayState, selectedTaskId]);

  const status = runState?.status ?? "pending";
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

  const handleActivityClick = (activity: RunActivity) => {
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
        className="flex items-center justify-between border-b border-[var(--line)] bg-[var(--card)] px-8 py-3"
        data-testid="run-header"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-1 text-xs text-[var(--muted)]">
            <Link href="/cohorts" className="hover:text-[var(--ink)]">Cohorts</Link>
            <span>›</span>
            {cohortId && (
              <>
                <Link
                  href={`/cohorts/${cohortId}`}
                  className="max-w-[180px] truncate hover:text-[var(--ink)]"
                  data-testid="run-breadcrumb-cohort"
                >
                  Cohort
                </Link>
                <span>›</span>
              </>
            )}
            <span className="font-mono text-[var(--ink)]">{runId.slice(0, 8)}…</span>
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <h1 className="max-w-[340px] truncate font-mono text-xl font-semibold tracking-[-0.02em]">
              {runState?.name ?? runId}
            </h1>
            <StatusBadge status={status as RunLifecycleStatus} />
            <span className="rounded bg-[var(--paper-2)] px-2 py-0.5 font-mono text-xs text-[var(--muted)]">
              {snapshotSequence === null ? "live" : `snapshot · seq ${snapshotSequence}`} · {formatSeconds(runState?.durationSeconds ?? null)}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {/* Key metrics */}
          <div className="hidden items-center gap-5 border-r border-[var(--line)] pr-3 lg:flex">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">Tasks</div>
              <span className="font-mono text-sm text-[var(--ink)]" data-testid="stat-tasks">
                {leafStatusCounts[TaskStatus.COMPLETED]}·{leafStatusCounts[TaskStatus.RUNNING]}·{leafStatusCounts[TaskStatus.READY]}·{leafStatusCounts[TaskStatus.PENDING]}
              </span>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">Tokens</div>
              <span className="font-mono text-sm text-[var(--ink)]" data-testid="stat-tokens">—</span>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">Cost</div>
              <span className="font-mono text-sm text-[var(--ink)]" data-testid="stat-cost">—</span>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">Score</div>
              <span className="font-mono text-sm text-[var(--ink)]" data-testid="stat-score">
                {formatPercent(runState?.finalScore ?? null)}
              </span>
            </div>
          </div>

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
          data-testid="run-staleness-banner"
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
            activities.length > 0 ? "with-timeline" : "without-timeline"
          }`}
          orientation="vertical"
          defaultLayout={activities.length > 0 ? verticalLayout : { "graph-workspace": 100 }}
          onLayoutChange={(layout) => {
            if (activities.length > 0) {
              setVerticalLayout(layout);
              savePanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, layout);
            }
          }}
          className="size-full"
        >
          <Panel
            id="graph-workspace"
            defaultSize={
              activities.length > 0
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
                  savePanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, layout);
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
                    runId={runId}
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

                  {!isInspectorOpen && (
                    <section
                      className="pointer-events-none absolute bottom-4 right-4 z-10 w-[260px] rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] bg-white/80 px-4 py-3 text-xs text-[var(--muted)]"
                      data-testid="workspace-launcher"
                    >
                      <div className="max-w-3xl space-y-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
                          Task inspection
                        </div>
                        <h2 className="text-sm font-semibold text-[var(--ink)]">
                          Click node → workspace drawer
                        </h2>
                        <p>State, outputs, turns, and evals appear scoped to the selected sequence.</p>
                        {selectedTask && (
                          <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] px-3 py-2">
                            Ready to inspect <span className="font-semibold text-[var(--ink)]">{selectedTask.name}</span>.
                          </div>
                        )}
                      </div>
                    </section>
                  )}
                </section>
              </Panel>

              {isInspectorOpen && (
                <>
                  <Separator
                    id="workspace-resize-handle"
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

          {activities.length > 0 && (
            <>
              <Separator
                id="timeline-resize-handle"
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
