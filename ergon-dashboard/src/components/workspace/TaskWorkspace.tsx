"use client";

import { useTaskDetails } from "@/hooks/useTaskDetails";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CommunicationPanel } from "@/components/panels/CommunicationPanel";
import { EvaluationPanel } from "@/components/panels/EvaluationPanel";
import { ResourcePanel } from "@/components/panels/ResourcePanel";
import { SandboxPanel } from "@/components/panels/SandboxPanel";
import { TaskTransitionLog } from "@/components/workspace/TaskTransitionLog";
import { ContextEventLog } from "@/features/graph/components/ContextEventLog";
import type { WorkflowRunState } from "@/lib/types";
import { formatTaskWallTimestamp } from "@/features/graph/utils/taskTiming";
import { filterTaskEvidenceForTime } from "./filterTaskEvidenceForTime";

function EmptySection({ message }: { message: string }) {
  return <div className="text-sm text-[#64707f]">{message}</div>;
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
      className="rounded-[9px] border border-[#e2e6ec] bg-white p-3"
      data-testid={testId}
    >
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98a2b1]">
        {title}
      </h3>
      {children}
    </section>
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
}: {
  runState: WorkflowRunState | null;
  taskId: string | null;
  error: string | null;
  onClearSelection?: () => void;
  onJumpToSequence?: (sequence: number) => void;
  selectedTime?: string | null;
  selectedSequence?: number | null;
}) {
  const { task, resources, executions, sandbox, threads, evaluation, dependencies, isLoading } =
    useTaskDetails(runState, taskId);

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
        className="flex h-full items-center justify-center p-8 text-center text-sm text-[#64707f]"
        data-testid="workspace-empty"
      >
        Select a task from the graph to open the focused task workspace.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex h-full items-center justify-center p-8 text-center text-sm text-[#64707f]"
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

  const primarySection =
    filteredEvidence.resources.length > 0
      ? "outputs"
      : filteredEvidence.evaluation
        ? "evaluation"
        : filteredEvidence.threads.length > 0
          ? "communication"
          : filteredEvidence.sandbox
            ? "sandbox"
            : "overview";

  const started = formatTaskWallTimestamp(task.startedAt);
  const ended = formatTaskWallTimestamp(task.completedAt);

  return (
    <div className="flex h-full min-h-0 flex-col bg-white" data-testid="task-workspace">
      <header
        className="shrink-0 border-b border-[#e2e6ec] bg-white p-4"
        data-testid="workspace-header"
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98a2b1]">
              Task workspace
            </div>
            <h2 className="truncate text-base font-semibold tracking-[-0.01em] text-[#0c1118]">{task.name}</h2>
          </div>
          <StatusBadge status={task.status} />
          {selectedSequence !== null && (
            <span
              className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-1 text-[11px] font-medium text-indigo-700"
              data-testid="workspace-timeline-badge"
            >
              Viewing seq {selectedSequence}
            </span>
          )}
          {onClearSelection && (
            <button
              type="button"
              onClick={onClearSelection}
              className="rounded-full border border-[#d7dce4] px-2 py-1 text-[11px] font-medium text-[#64707f] transition-colors hover:bg-[#f6f7f9]"
              data-testid="workspace-close"
            >
              Close
            </button>
          )}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px] text-[#64707f]">
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
                className="text-[#0c1118]"
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
                className="text-[#0c1118]"
              >
                {ended.text}
              </time>
            ) : (
              ended.text
            )}
          </span>
        </div>
        {task.description && (
          <p className="mt-3 text-xs leading-5 text-[#64707f]">{task.description}</p>
        )}
      </header>

      <div className="min-h-0 space-y-3 overflow-y-auto p-3" data-testid="workspace-scroll-region">
        <WorkspaceSection testId="workspace-transitions" title="State transitions">
          <TaskTransitionLog task={task} onJumpToSequence={onJumpToSequence} />
        </WorkspaceSection>

        <WorkspaceSection testId="workspace-actions" title="Actions">
          <ContextEventLog events={filteredEvidence.contextEvents} />
        </WorkspaceSection>

        <div data-testid="workspace-primary">
          {primarySection === "outputs" && (
            <WorkspaceSection testId="workspace-outputs" title="Outputs">
              <ResourcePanel resources={filteredEvidence.resources} runId={runState?.id ?? null} />
            </WorkspaceSection>
          )}
          {primarySection === "evaluation" && (
            <WorkspaceSection testId="workspace-evaluation" title="Evaluation">
              <EvaluationPanel evaluation={filteredEvidence.evaluation} />
            </WorkspaceSection>
          )}
          {primarySection === "communication" && (
            <WorkspaceSection testId="workspace-communication" title="Communication">
              <CommunicationPanel threads={filteredEvidence.threads} />
            </WorkspaceSection>
          )}
          {primarySection === "sandbox" && (
            <WorkspaceSection testId="workspace-sandbox" title="Sandbox">
              <SandboxPanel sandbox={filteredEvidence.sandbox} />
            </WorkspaceSection>
          )}
          {primarySection === "overview" && (
            <WorkspaceSection testId="workspace-primary-overview" title="Overview">
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
          )}
        </div>

        <div className="grid gap-3">
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
                        Started: {execution.startedAt ? new Date(execution.startedAt).toLocaleTimeString() : "—"}
                      </span>
                      <span>
                        Completed: {execution.completedAt ? new Date(execution.completedAt).toLocaleTimeString() : "—"}
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

          {primarySection !== "communication" && (
            <WorkspaceSection testId="workspace-communication" title="Communication">
              <CommunicationPanel threads={filteredEvidence.threads} />
            </WorkspaceSection>
          )}

          {primarySection !== "outputs" && (
            <WorkspaceSection testId="workspace-outputs" title="Outputs">
              <ResourcePanel resources={filteredEvidence.resources} runId={runState?.id ?? null} />
            </WorkspaceSection>
          )}

          {primarySection !== "evaluation" && (
            <WorkspaceSection testId="workspace-evaluation" title="Evaluation">
              <EvaluationPanel evaluation={filteredEvidence.evaluation} />
            </WorkspaceSection>
          )}

          {primarySection !== "sandbox" && (
            <WorkspaceSection testId="workspace-sandbox" title="Sandbox">
              <SandboxPanel sandbox={filteredEvidence.sandbox} />
            </WorkspaceSection>
          )}

        </div>
      </div>
    </div>
  );
}
