"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { DAGCanvas } from "@/components/dag/DAGCanvas";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RunStatusBar } from "@/components/run/RunStatusBar";
import { UnifiedEventStream } from "@/components/run/UnifiedEventStream";
import { TaskWorkspace } from "@/components/workspace/TaskWorkspace";
import { ActivityStackTimeline } from "@/features/activity/components/ActivityStackTimeline";
import { buildRunActivities } from "@/features/activity/buildRunActivities";
import type { RunActivity } from "@/features/activity/types";
import {
  parseGraphMutationDtoArray,
  type GraphMutationDto,
} from "@/features/graph/contracts/graphMutations";
import { replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { useCohortDetail } from "@/hooks/useCohortDetail";
import { useRunState } from "@/hooks/useRunState";
import { buildRunEvents } from "@/lib/runEvents";
import type { WorkflowRunState } from "@/lib/types";
import { CohortDetail, RunLifecycleStatus, SerializedWorkflowRunState, TaskStatus } from "@/lib/types";

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
  initialCohortDetail = null,
}: {
  runId: string;
  cohortId?: string;
  initialRunState?: SerializedWorkflowRunState | null;
  initialCohortDetail?: CohortDetail | null;
}) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null);
  const [isStreamOpen, setIsStreamOpen] = useState(false);
  const { runState, isLoading, error, isSubscribed } = useRunState(runId, initialRunState);
  const { detail } = useCohortDetail(cohortId ?? "", initialCohortDetail);

  // Timeline playback state
  const [timelineMode, setTimelineMode] = useState<"live" | "timeline">("live");
  const [currentSequence, setCurrentSequence] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [mutations, setMutations] = useState<GraphMutationDto[]>([]);
  const snapshotCache = useRef(new Map<number, WorkflowRunState>());
  const requestedSequenceRef = useRef<number | null>(null);

  // Fetch mutations when entering timeline mode
  useEffect(() => {
    if (timelineMode !== "timeline") return;
    let cancelled = false;
    fetch(`/api/runs/${runId}/mutations`)
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const parsed = parseGraphMutationDtoArray(data);
        setMutations(parsed);
        snapshotCache.current.clear();
        const requestedSequence = requestedSequenceRef.current;
        requestedSequenceRef.current = null;
        const defaultMutation = parsed[parsed.length - 1] ?? null;
        const requestedMutation =
          requestedSequence === null
            ? null
            : nearestMutationAtOrBefore(parsed, requestedSequence);
        setCurrentSequence((requestedMutation ?? defaultMutation)?.sequence ?? 0);
      })
      .catch(() => {
        if (!cancelled) setMutations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [timelineMode, runId]);

  // Build display state: replay for timeline mode, live state otherwise
  const displayState = useMemo(() => {
    if (timelineMode === "live" || mutations.length === 0) return runState;
    if (!runState) return runState;
    const emptyState: WorkflowRunState = {
      ...runState,
      tasks: new Map(),
      totalTasks: 0,
      totalLeafTasks: 0,
      completedTasks: 0,
      runningTasks: 0,
      failedTasks: 0,
    };
    return replayToSequence(
      mutations,
      currentSequence,
      emptyState,
      snapshotCache.current,
    );
  }, [timelineMode, runState, mutations, currentSequence]);

  const runRow = useMemo(() => {
    if (!cohortId || !detail) return null;
    return detail.runs.find((run) => run.run_id === runId) ?? null;
  }, [cohortId, detail, runId]);

  const selectedTask = useMemo(() => {
    if (!displayState || !selectedTaskId) return null;
    return displayState.tasks.get(selectedTaskId) ?? null;
  }, [displayState, selectedTaskId]);

  // D7: status counts for the RunStatusBar. Only leaf tasks so the totals
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

  // D4: Unified event log — derived from displayState so timeline scrubbing
  // trims the feed in lockstep.
  const events = useMemo(() => buildRunEvents(displayState), [displayState]);

  const activities = useMemo(
    () =>
      buildRunActivities({
        runState: displayState,
        events,
        mutations,
        currentSequence: timelineMode === "timeline" ? currentSequence : null,
      }),
    [displayState, events, mutations, timelineMode, currentSequence],
  );

  const selectedTimelineTime = useMemo(() => {
    if (timelineMode !== "timeline") return null;
    return nearestMutationAtOrBefore(mutations, currentSequence)?.created_at ?? null;
  }, [timelineMode, mutations, currentSequence]);

  const highlightedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    if (selectedTaskId) ids.add(selectedTaskId);
    const selectedActivity = activities.find((activity) => activity.id === selectedActivityId);
    if (selectedActivity?.taskId) ids.add(selectedActivity.taskId);
    return ids;
  }, [activities, selectedActivityId, selectedTaskId]);

  // D7: keyboard shortcuts — Esc closes selection, `t` toggles timeline,
  // `e` toggles event stream, `1-6` filters by lifecycle status.
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
        if (selectedTaskId) setSelectedTaskId(null);
        else if (statusFilter) setStatusFilter(null);
        return;
      }
      if (e.key === "t" || e.key === "T") {
        setTimelineMode((prev) => (prev === "live" ? "timeline" : "live"));
        if (timelineMode === "timeline") setIsPlaying(false);
        return;
      }
      if (e.key === "e" || e.key === "E") {
        setIsStreamOpen((prev) => !prev);
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
  }, [selectedTaskId, statusFilter, timelineMode]);

  useEffect(() => {
    if (!selectedTaskId || !displayState) return;
    if (!displayState.tasks.has(selectedTaskId)) {
      setSelectedTaskId(null);
      setSelectionNotice("The selected task disappeared from the latest run topology, so the inspector was reset.");
    }
  }, [displayState, selectedTaskId]);

  const status = runState?.status ?? runRow?.status ?? "pending";
  const isInspectorOpen = selectedTaskId !== null;

  const handleTaskClick = (taskId: string) => {
    setSelectionNotice(null);
    setSelectedActivityId(null);
    setSelectedTaskId((prev) => (prev === taskId ? null : taskId));
  };

  const handleSequenceChange = (sequence: number) => {
    const mutation = nearestMutationAtOrBefore(mutations, sequence);
    setCurrentSequence(mutation?.sequence ?? sequence);
  };

  const handleActivityClick = (activity: RunActivity) => {
    setSelectionNotice(null);
    setSelectedActivityId(activity.id);
    if (activity.sequence !== null) {
      requestedSequenceRef.current = activity.sequence;
      if (timelineMode !== "timeline") setTimelineMode("timeline");
      handleSequenceChange(activity.sequence);
    }
    if (activity.taskId) {
      setSelectedTaskId(activity.taskId);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#f6f7f9] text-[#0c1118]">
      <header
        className="h-14 border-b border-[#e2e6ec] bg-white"
        data-testid="run-header"
      >
        <div className="flex h-full w-full items-center justify-between gap-4 px-4">
          <div className="flex min-w-0 items-center gap-4">
            <Link href="/" className="flex items-center gap-2 text-sm font-semibold text-[#0c1118]">
              <span className="inline-block size-4 rounded bg-[#0c1118]" aria-hidden />
              Ergon
            </Link>
            <div className="flex min-w-0 items-center gap-2 truncate text-xs text-[#64707f]">
              <Link href="/" className="hover:text-[#0c1118]">
                Cohorts
              </Link>
            {cohortId && (
              <>
                <span>/</span>
                <Link
                  href={`/cohorts/${cohortId}`}
                    className="max-w-[180px] truncate hover:text-[#0c1118]"
                  data-testid="run-breadcrumb-cohort"
                >
                  {detail?.summary.name ?? "Cohort"}
                </Link>
              </>
            )}
            <span>/</span>
              <span className="font-mono text-[#1f2733]">{runId.slice(0, 8)}...</span>
            </div>

            <div className="flex min-w-0 items-center gap-2">
              <h1 className="max-w-[260px] truncate text-sm font-semibold tracking-[-0.01em] text-[#0c1118]">
                {runState?.name ?? runRow?.run_id ?? "Run"}
              </h1>
              <StatusBadge status={status as RunLifecycleStatus} />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            <div className="hidden items-center gap-3 text-[11px] uppercase tracking-[0.08em] text-[#98a2b1] lg:flex">
              <span>
                Tasks <b className="ml-1 font-mono text-[#0c1118]">{runState?.totalTasks ?? "—"}</b>
              </span>
              <span>
                Turns <b className="ml-1 font-mono text-[#0c1118]">{runState?.completedTasks ?? 0}</b>
              </span>
              <span>
                Score <b className="ml-1 font-mono text-[#0c1118]">{formatPercent(runState?.finalScore ?? runRow?.final_score ?? null)}</b>
              </span>
            </div>
                <div
                  role="tablist"
                  aria-label="Run view mode"
              className="inline-flex rounded-md border border-[#e2e6ec] bg-[#f6f7f9] p-0.5 text-xs font-medium"
                >
                  {(["live", "timeline"] as const).map((mode) => {
                    const active = timelineMode === mode;
                    return (
                      <button
                        key={mode}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        onClick={() => {
                          if (mode === timelineMode) return;
                          setTimelineMode(mode);
                          if (mode === "live") setIsPlaying(false);
                        }}
                  className={`rounded px-2.5 py-1 transition-colors ${
                          active
                      ? "bg-white text-[#0c1118] shadow-sm"
                      : "text-[#64707f] hover:text-[#0c1118]"
                        }`}
                        data-testid={`mode-${mode}`}
                      >
                        {mode === "live" ? "Live" : "Timeline"}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  onClick={() => setIsStreamOpen((p) => !p)}
                  aria-pressed={isStreamOpen}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    isStreamOpen
                  ? "bg-[#0c1118] text-white"
                  : "border border-[#e2e6ec] bg-white text-[#64707f] hover:bg-[#eef0f3]"
                  }`}
                  title="Toggle event stream (e)"
                  data-testid="event-stream-toggle"
                >
              {isStreamOpen ? "Hide events" : "Event tracks"}
                </button>
          </div>

          {leafTotal > 0 && (
            <div className="absolute left-4 right-4 top-16 z-20">
              <RunStatusBar
                counts={leafStatusCounts}
                total={leafTotal}
                activeFilter={statusFilter}
                onFilter={setStatusFilter}
              />
            </div>
          )}

          {error && (
            <div
              className="absolute left-4 right-4 top-16 z-30 rounded-md border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
              data-testid="run-staleness-banner"
            >
              {error}
            </div>
          )}
        </div>
      </header>

      <main
        className="relative min-h-0 flex-1 overflow-hidden px-2 pb-[252px] pt-8"
      >
        {selectionNotice && (
          <div
            className="absolute left-4 right-4 top-4 z-40 rounded-md border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
            data-testid="selection-reset-notice"
          >
            {selectionNotice}
          </div>
        )}
        <section
          className="h-[calc(100vh-340px)] min-h-[430px] overflow-hidden rounded-[10px] border border-[#e2e6ec] bg-white"
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
        </section>

        {activities.length > 0 && (
          <section
            className="fixed inset-x-0 bottom-0 z-30 border-t border-[#18202b] bg-[#070b12]"
            data-testid="timeline-region"
          >
            <ActivityStackTimeline
              activities={activities}
              mutations={mutations}
              currentSequence={currentSequence}
              onSequenceChange={handleSequenceChange}
              selectedTaskId={selectedTaskId}
              selectedActivityId={selectedActivityId}
              isPlaying={isPlaying}
              onTogglePlay={() => setIsPlaying((p) => !p)}
              speed={playbackSpeed}
              onSpeedChange={setPlaybackSpeed}
              onActivityClick={handleActivityClick}
            />
          </section>
        )}

        {isStreamOpen && events.length > 0 && (
          <section
            className="absolute bottom-[370px] left-4 z-20 max-h-[44vh] w-[520px] overflow-hidden rounded-[10px] border border-[#e2e6ec] bg-white shadow-[0_8px_24px_rgb(12_17_24/0.08)]"
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
                if (timelineMode !== "timeline") setTimelineMode("timeline");
                requestedSequenceRef.current = seq;
                handleSequenceChange(seq);
              }}
            />
          </section>
        )}

        {isInspectorOpen ? (
          <section
            className="absolute bottom-[370px] right-4 top-4 z-20 w-[360px] overflow-hidden rounded-[10px] border border-[#e2e6ec] bg-white shadow-[0_8px_24px_rgb(12_17_24/0.08)]"
            data-testid="workspace-region"
          >
            <TaskWorkspace
              runState={displayState}
              taskId={selectedTaskId}
              error={error}
              onClearSelection={() => setSelectedTaskId(null)}
              onJumpToSequence={(seq) => {
                if (timelineMode !== "timeline") setTimelineMode("timeline");
                requestedSequenceRef.current = seq;
                handleSequenceChange(seq);
              }}
              selectedTime={selectedTimelineTime}
              selectedSequence={timelineMode === "timeline" ? currentSequence : null}
            />
          </section>
        ) : (
          <section
            className="pointer-events-none absolute bottom-[370px] right-4 z-10 w-[260px] rounded-[10px] border border-dashed border-[#cdd3dc] bg-white/80 px-4 py-3 text-xs text-[#64707f]"
            data-testid="workspace-launcher"
          >
            <div className="max-w-3xl space-y-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98a2b1]">
                Task inspection
              </div>
              <h2 className="text-sm font-semibold text-[#0c1118]">
                Click node {"->"} workspace drawer
              </h2>
              <p>State, outputs, turns, and evals appear scoped to the selected sequence.</p>
              {selectedTask && (
                <div className="rounded-md border border-[#e2e6ec] bg-[#f6f7f9] px-3 py-2">
                  Ready to inspect <span className="font-semibold text-[#0c1118]">{selectedTask.name}</span>.
                </div>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
