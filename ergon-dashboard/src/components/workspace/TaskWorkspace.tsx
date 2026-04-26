"use client";

import { useEffect, useRef, useState } from "react";

import { useTaskDetails } from "@/hooks/useTaskDetails";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CommunicationPanel } from "@/components/panels/CommunicationPanel";
import { EvaluationPanel } from "@/components/panels/EvaluationPanel";
import { ResourcePanel } from "@/components/panels/ResourcePanel";
import { SandboxPanel } from "@/components/panels/SandboxPanel";
import { TaskTransitionLog } from "@/components/workspace/TaskTransitionLog";
import { ContextEventLog } from "@/features/graph/components/ContextEventLog";
import type { RunActivity } from "@/features/activity/types";
import type { WorkflowRunState } from "@/lib/types";
import { formatClockTime } from "@/lib/timeFormat";
import { formatTaskWallTimestamp } from "@/features/graph/utils/taskTiming";
import { filterTaskEvidenceForTime } from "./filterTaskEvidenceForTime";

function EmptySection({ message }: { message: string }) {
  return <div className="text-sm text-[var(--muted)]">{message}</div>;
}

const ACTIVITY_KIND_TITLE: Record<RunActivity["kind"], string> = {
  execution: "Execution",
  graph: "Graph mutation",
  message: "Message",
  artifact: "Artifact",
  evaluation: "Evaluation",
  context: "Context event",
  sandbox: "Sandbox",
};

function ActivityDetail({ activity }: { activity: RunActivity }) {
  const metadata = Object.entries(activity.metadata)
    .filter(([, value]) => value !== null && value !== "")
    .slice(0, 4);
  const debugPayload = JSON.stringify(activity.debug, null, 2);

  return (
    <section
      className="mt-3 rounded-[var(--radius-sm)] border border-[var(--accent-soft)] bg-[var(--accent-soft)]/45 p-3 text-xs"
      data-testid="workspace-activity-detail"
    >
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--accent)]">
        Selected activity
      </div>
      <div className="font-semibold text-[var(--ink)]">
        {ACTIVITY_KIND_TITLE[activity.kind]}: {activity.label}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[var(--muted)]">
        <span>Band: {activity.band}</span>
        <span>Source: {activity.sourceKind}</span>
        <span>Actor: {activity.actor ?? "—"}</span>
        <span>Started: {formatClockTime(activity.startAt)}</span>
        <span>Sequence: {activity.sequence ?? "—"}</span>
        <span>Task: {activity.lineage.taskId ?? "—"}</span>
        <span>Execution: {activity.lineage.taskExecutionId ?? "—"}</span>
        <span>Sandbox: {activity.lineage.sandboxId ?? "—"}</span>
        {activity.endAt && <span>Ended: {formatClockTime(activity.endAt)}</span>}
        {metadata.map(([key, value]) => (
          <span key={key} className="truncate" title={String(value)}>
            {key}: {String(value)}
          </span>
        ))}
      </div>
      <details className="mt-3 rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] p-2">
        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
          Raw JSON
        </summary>
        <code className="mt-2 block max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-[var(--muted)]">
          {debugPayload}
        </code>
      </details>
    </section>
  );
}

function WorkspaceSection({
  testId,
  title,
  children,
}: {
  testId: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--card)] p-3"
      data-testid={testId}
    >
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
        {title}
      </h3>
      {children}
    </section>
  );
}

type WorkspaceTabId = "overview" | "actions" | "communication" | "outputs" | "transitions" | "evaluation";

const WORKSPACE_TABS: Array<{
  id: WorkspaceTabId;
  label: string;
  testId: string;
}> = [
  { id: "overview", label: "Overview", testId: "workspace-tab-overview" },
  { id: "actions", label: "Actions", testId: "workspace-tab-actions" },
  { id: "communication", label: "Communication", testId: "workspace-tab-communication" },
  { id: "outputs", label: "Outputs", testId: "workspace-tab-outputs" },
  { id: "transitions", label: "Transitions", testId: "workspace-tab-transitions" },
  { id: "evaluation", label: "Evaluation", testId: "workspace-tab-evaluation" },
];

function workspaceTabButtonId(id: WorkspaceTabId) {
  return `workspace-tab-button-${id}`;
}

function workspaceTabPanelId(id: WorkspaceTabId) {
  return `workspace-tab-panel-${id}`;
}

function WorkspaceTabPanel({
  tabId,
  children,
}: {
  tabId: WorkspaceTabId;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={workspaceTabPanelId(tabId)}
      aria-labelledby={workspaceTabButtonId(tabId)}
      tabIndex={0}
    >
      {children}
    </div>
  );
}

export function TaskWorkspace({
  runState,
  taskId,
  error,
  onClearSelection,
  onJumpToSequence,
  selectedTime = null,
  selectedSequence = null,
  selectedActivity = null,
}: {
  runState: WorkflowRunState | null;
  taskId: string | null;
  error: string | null;
  onClearSelection?: () => void;
  onJumpToSequence?: (sequence: number) => void;
  selectedTime?: string | null;
  selectedSequence?: number | null;
  selectedActivity?: RunActivity | null;
}) {
  const { task, resources, executions, sandbox, threads, evaluation, dependencies, isLoading } =
    useTaskDetails(runState, taskId);
  const [activeTab, setActiveTab] = useState<WorkspaceTabId>("overview");
  const tabButtonRefs = useRef<Record<WorkspaceTabId, HTMLButtonElement | null>>({
    overview: null,
    actions: null,
    communication: null,
    outputs: null,
    transitions: null,
    evaluation: null,
  });

  useEffect(() => {
    setActiveTab("overview");
  }, [taskId]);

  function activateTab(tabId: WorkspaceTabId, shouldFocus = false) {
    setActiveTab(tabId);
    if (shouldFocus) {
      requestAnimationFrame(() => tabButtonRefs.current[tabId]?.focus());
    }
  }

  function handleTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, tabId: WorkspaceTabId) {
    const currentIndex = WORKSPACE_TABS.findIndex((tab) => tab.id === tabId);
    if (currentIndex === -1) return;

    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % WORKSPACE_TABS.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + WORKSPACE_TABS.length) % WORKSPACE_TABS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = WORKSPACE_TABS.length - 1;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    activateTab(WORKSPACE_TABS[nextIndex].id, true);
  }

  const contextEvents = taskId && runState ? (runState.contextEventsByTask.get(taskId) ?? []) : [];
  const filteredEvidence = filterTaskEvidenceForTime({
    resources,
    executions,
    sandbox,
    threads,
    evaluation,
    contextEvents,
    selectedTime,
  });

  if (!taskId) {
    return (
      <div
        className="flex h-full items-center justify-center p-8 text-center text-sm text-[var(--muted)]"
        data-testid="workspace-empty"
      >
        Select a task from the graph to open the focused task workspace.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex h-full items-center justify-center p-8 text-center text-sm text-[var(--muted)]"
        data-testid="workspace-loading"
      >
        Loading task workspace...
      </div>
    );
  }

  if (!task || error) {
    return (
      <div
        className="flex h-full items-center justify-center p-8 text-center text-sm text-red-600"
        data-testid="workspace-error"
      >
        {error ?? "Task not found"}
      </div>
    );
  }

  const started = formatTaskWallTimestamp(task.startedAt);
  const ended = formatTaskWallTimestamp(task.completedAt);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--card)]" data-testid="task-workspace">
      <header
        className="shrink-0 border-b border-[var(--line)] bg-[var(--card)] p-4"
        data-testid="workspace-header"
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
              Task workspace
            </div>
            <h2 className="truncate text-base font-semibold tracking-[-0.01em] text-[var(--ink)]">{task.name}</h2>
          </div>
          <StatusBadge status={task.status} />
          {selectedSequence !== null && (
            <span
              className="rounded-full border border-[var(--accent-soft)] bg-[var(--accent-soft)] px-2 py-1 text-[11px] font-medium text-[var(--accent-ink)]"
              data-testid="workspace-timeline-badge"
            >
              Viewing seq {selectedSequence}
            </span>
          )}
          {onClearSelection && (
            <button
              type="button"
              onClick={onClearSelection}
              className="rounded-full border border-[var(--line)] px-2 py-1 text-[11px] font-medium text-[var(--muted)] transition-colors hover:bg-[var(--paper)]"
              data-testid="workspace-close"
            >
              Close · Esc
            </button>
          )}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px] text-[var(--muted)]">
          <span>Worker: {task.assignedWorkerName ?? "—"}</span>
          <span>Level: {task.level}</span>
          <span>Leaf task: {task.isLeaf ? "yes" : "no"}</span>
          <span>Attempts: {filteredEvidence.executions.length || 0}</span>
          <span>Outputs: {filteredEvidence.resources.length}</span>
          <span className="tabular-nums">
            Started:{" "}
            {started.dateTime ? (
              <time
                dateTime={started.dateTime}
                title={started.dateTime}
                className="text-[var(--ink)]"
              >
                {started.text}
              </time>
            ) : (
              started.text
            )}
          </span>
          <span className="tabular-nums">
            Ended:{" "}
            {ended.dateTime ? (
              <time
                dateTime={ended.dateTime}
                title={ended.dateTime}
                className="text-[var(--ink)]"
              >
                {ended.text}
              </time>
            ) : (
              ended.text
            )}
          </span>
        </div>
        {task.description && (
          <p className="mt-3 text-xs leading-5 text-[var(--muted)]">{task.description}</p>
        )}
        {selectedActivity && <ActivityDetail activity={selectedActivity} />}
      </header>

      <div
        role="tablist"
        aria-label="Workspace sections"
        className="flex shrink-0 gap-1 overflow-x-auto border-b border-[var(--line)] bg-[var(--card)] px-3 py-2"
        data-testid="workspace-tabs"
      >
        {WORKSPACE_TABS.map((tab) => {
          const selected = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              ref={(button) => {
                tabButtonRefs.current[tab.id] = button;
              }}
              id={workspaceTabButtonId(tab.id)}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={workspaceTabPanelId(tab.id)}
              tabIndex={selected ? 0 : -1}
              onClick={() => activateTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, tab.id)}
              className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                selected
                  ? "bg-[var(--ink)] text-[var(--paper)]"
                  : "text-[var(--muted)] hover:bg-[var(--paper)] hover:text-[var(--ink)]"
              }`}
              data-testid={tab.testId}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 space-y-3 overflow-y-auto p-3" data-testid="workspace-scroll-region">
        {activeTab === "overview" && (
          <WorkspaceTabPanel tabId="overview">
            <WorkspaceSection testId="workspace-overview" title="Overview">
              <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">Waiting on</div>
                  {dependencies.waitingOn.length === 0 ? (
                    <EmptySection message="No blocking dependencies." />
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {dependencies.waitingOn.map((dep) => (
                        <li key={dep.id}>{dep.name}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">Blocking</div>
                  {dependencies.blocking.length === 0 ? (
                    <EmptySection message="No dependent tasks." />
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {dependencies.blocking.map((dep) => (
                        <li key={dep.id}>{dep.name}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}

        {activeTab === "actions" && (
          <WorkspaceTabPanel tabId="actions">
            <WorkspaceSection testId="workspace-actions" title="Actions">
              <div className="space-y-3">
                <ContextEventLog events={filteredEvidence.contextEvents} />

                <WorkspaceSection testId="workspace-executions" title="Executions">
                  {filteredEvidence.executions.length === 0 ? (
                    <EmptySection message="No execution attempts recorded yet." />
                  ) : (
                    <div className="space-y-3">
                      {filteredEvidence.executions.map((execution) => (
                        <div
                          key={execution.id}
                          className="rounded-xl border border-gray-200 p-3 dark:border-gray-700"
                        >
                          <div className="flex items-center gap-2">
                            <div className="text-sm font-semibold text-gray-900 dark:text-white">
                              Attempt {execution.attemptNumber}
                            </div>
                            <StatusBadge status={execution.status} size="sm" />
                          </div>
                          <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
                            <span>Agent: {execution.agentName ?? "—"}</span>
                            <span>
                              Started: {execution.startedAt ? formatClockTime(execution.startedAt) : "—"}
                            </span>
                            <span>
                              Completed: {execution.completedAt ? formatClockTime(execution.completedAt) : "—"}
                            </span>
                          </div>
                          {execution.errorMessage && (
                            <div className="mt-2 text-sm text-red-600 dark:text-red-400">
                              {execution.errorMessage}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </WorkspaceSection>

                <WorkspaceSection testId="workspace-sandbox" title="Sandbox">
                  <SandboxPanel sandbox={filteredEvidence.sandbox} />
                </WorkspaceSection>
              </div>
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}

        {activeTab === "communication" && (
          <WorkspaceTabPanel tabId="communication">
            <WorkspaceSection testId="workspace-communication" title="Communication">
              <CommunicationPanel threads={filteredEvidence.threads} />
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}

        {activeTab === "outputs" && (
          <WorkspaceTabPanel tabId="outputs">
            <WorkspaceSection testId="workspace-outputs" title="Outputs">
              <ResourcePanel resources={filteredEvidence.resources} runId={runState?.id ?? null} />
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}

        {activeTab === "transitions" && (
          <WorkspaceTabPanel tabId="transitions">
            <WorkspaceSection testId="workspace-transitions" title="State transitions">
              <TaskTransitionLog task={task} onJumpToSequence={onJumpToSequence} />
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}

        {activeTab === "evaluation" && (
          <WorkspaceTabPanel tabId="evaluation">
            <WorkspaceSection testId="workspace-evaluation" title="Evaluation">
              <EvaluationPanel evaluation={filteredEvidence.evaluation} />
            </WorkspaceSection>
          </WorkspaceTabPanel>
        )}
      </div>
    </div>
  );
}
