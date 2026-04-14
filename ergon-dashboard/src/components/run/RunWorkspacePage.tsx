"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DAGCanvas } from "@/components/dag/DAGCanvas";
import { StatusBadge } from "@/components/common/StatusBadge";
import { TaskWorkspace } from "@/components/workspace/TaskWorkspace";
import { MutationTimeline } from "@/features/graph/components/MutationTimeline";
import {
  parseGraphMutationDtoArray,
  type GraphMutationDto,
} from "@/features/graph/contracts/graphMutations";
import { replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { useCohortDetail } from "@/hooks/useCohortDetail";
import { useRunState } from "@/hooks/useRunState";
import type { WorkflowRunState } from "@/lib/types";
import { CohortDetail, RunLifecycleStatus, SerializedWorkflowRunState } from "@/lib/types";

function formatSeconds(value: number | null): string {
  if (value == null) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${(value / 60).toFixed(1)}m`;
}

function formatPercent(value: number | null): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
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
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const { runState, isLoading, error, isSubscribed } = useRunState(runId, initialRunState);
  const { detail } = useCohortDetail(cohortId ?? "", initialCohortDetail);

  // Timeline playback state
  const [timelineMode, setTimelineMode] = useState<"live" | "timeline">("live");
  const [currentSequence, setCurrentSequence] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [mutations, setMutations] = useState<GraphMutationDto[]>([]);
  const snapshotCache = useRef(new Map<number, WorkflowRunState>());

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
        setCurrentSequence(
          parsed.length > 0 ? parsed[parsed.length - 1].sequence : 0,
        );
      })
      .catch(() => {
        if (!cancelled) setMutations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [timelineMode, runId]);

  const handleToggleTimeline = useCallback(() => {
    setTimelineMode((prev) => {
      if (prev === "live") return "timeline";
      setIsPlaying(false);
      return "live";
    });
  }, []);

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
    setSelectedTaskId((prev) => (prev === taskId ? null : taskId));
  };

  return (
    <div className="flex min-h-screen flex-col bg-gray-50 dark:bg-gray-950">
      <header
        className="border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
        data-testid="run-header"
      >
        <div className="w-full px-6 py-5">
          <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
            <Link href="/" className="hover:text-gray-900 dark:hover:text-white">
              Experiment Cohorts
            </Link>
            {cohortId && (
              <>
                <span>/</span>
                <Link
                  href={`/cohorts/${cohortId}`}
                  className="hover:text-gray-900 dark:hover:text-white"
                  data-testid="run-breadcrumb-cohort"
                >
                  {detail?.summary.name ?? "Cohort"}
                </Link>
              </>
            )}
            <span>/</span>
            <span className="font-mono text-gray-700 dark:text-gray-200">{runId.slice(0, 8)}...</span>
          </div>

          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {runState?.name ?? runRow?.run_id ?? "Run"}
                </h1>
                <StatusBadge status={status as RunLifecycleStatus} />
                <button
                  onClick={handleToggleTimeline}
                  className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
                    timelineMode === "timeline"
                      ? "bg-blue-600 text-white dark:bg-blue-500"
                      : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  }`}
                  data-testid="timeline-toggle"
                >
                  {timelineMode === "timeline" ? "Live" : "Timeline"}
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
                <span>Workflow: {runState?.name ?? "—"}</span>
                <span suppressHydrationWarning>Started: {runState?.startedAt ? new Date(runState.startedAt).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" }) : "—"}</span>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50">
                <dt className="text-xs text-gray-500 dark:text-gray-400">Runtime</dt>
                <dd className="text-sm font-semibold text-gray-900 dark:text-white">
                  {formatSeconds(runState?.durationSeconds ?? (runRow?.running_time_ms != null ? runRow.running_time_ms / 1000 : null))}
                </dd>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50">
                <dt className="text-xs text-gray-500 dark:text-gray-400">Score</dt>
                <dd className="text-sm font-semibold text-gray-900 dark:text-white">
                  {formatPercent(runState?.finalScore ?? runRow?.final_score ?? null)}
                </dd>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50">
                <dt className="text-xs text-gray-500 dark:text-gray-400">Tasks</dt>
                <dd className="text-sm font-semibold text-gray-900 dark:text-white">
                  {runState?.totalTasks ?? "—"}
                </dd>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50">
                <dt className="text-xs text-gray-500 dark:text-gray-400">Failed tasks</dt>
                <dd className="text-sm font-semibold text-gray-900 dark:text-white">
                  {runState?.failedTasks ?? "—"}
                </dd>
              </div>
            </dl>
          </div>

          {error && (
            <div
              className="mt-4 rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300"
              data-testid="run-staleness-banner"
            >
              {error}
            </div>
          )}
        </div>
      </header>

      <main
        className={`flex-1 w-full gap-6 px-6 py-6 ${
          isInspectorOpen
            ? "grid xl:min-h-0 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-rows-[auto_minmax(0,1fr)]"
            : "space-y-6"
        }`}
      >
        {selectionNotice && (
          <div
            className="rounded-2xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200 xl:col-span-2"
            data-testid="selection-reset-notice"
          >
            {selectionNotice}
          </div>
        )}
        <section
          className={`min-h-[72vh] rounded-3xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900 ${
            isInspectorOpen ? "xl:h-full xl:min-h-0" : "h-[78vh]"
          }`}
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
          />
        </section>

        {timelineMode === "timeline" && mutations.length > 0 && (
          <section
            className="rounded-3xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900 xl:col-span-2"
            data-testid="timeline-region"
          >
            <MutationTimeline
              mutations={mutations}
              currentSequence={currentSequence}
              onSequenceChange={setCurrentSequence}
              isPlaying={isPlaying}
              onTogglePlay={() => setIsPlaying((p) => !p)}
              speed={playbackSpeed}
              onSpeedChange={setPlaybackSpeed}
            />
          </section>
        )}

        {isInspectorOpen ? (
          <section className="min-h-[72vh] xl:h-full xl:min-h-0" data-testid="workspace-region">
            <TaskWorkspace
              runState={displayState}
              taskId={selectedTaskId}
              error={error}
              onClearSelection={() => setSelectedTaskId(null)}
            />
          </section>
        ) : (
          <section
            className="rounded-3xl border border-dashed border-gray-300 bg-white px-6 py-8 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
            data-testid="workspace-launcher"
          >
            <div className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-400">
                Task inspection
              </div>
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                Graph first, then open a focused task workspace
              </h2>
              <p>
                Select a task node to inspect its outputs, execution attempts, actions,
                communication, and evaluation without keeping the entire page in a cramped
                permanent split view.
              </p>
              {selectedTask && (
                <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800/50">
                  Ready to inspect <span className="font-semibold text-gray-900 dark:text-white">{selectedTask.name}</span>.
                </div>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
