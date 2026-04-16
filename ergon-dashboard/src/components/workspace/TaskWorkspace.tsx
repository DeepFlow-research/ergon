"use client";

import { useTaskDetails } from "@/hooks/useTaskDetails";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CommunicationPanel } from "@/components/panels/CommunicationPanel";
import { EvaluationPanel } from "@/components/panels/EvaluationPanel";
import { GenerationTracePanel } from "@/components/panels/GenerationTracePanel";
import { ResourcePanel } from "@/components/panels/ResourcePanel";
import { SandboxPanel } from "@/components/panels/SandboxPanel";
import { TaskTransitionLog } from "@/components/workspace/TaskTransitionLog";
import type { WorkflowRunState } from "@/lib/types";
import { formatTaskWallTimestamp } from "@/features/graph/utils/taskTiming";

function EmptySection({ message }: { message: string }) {
  return <div className="text-sm text-gray-500 dark:text-gray-400">{message}</div>;
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
      className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      data-testid={testId}
    >
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
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
}: {
  runState: WorkflowRunState | null;
  taskId: string | null;
  error: string | null;
  onClearSelection?: () => void;
  onJumpToSequence?: (sequence: number) => void;
}) {
  const { task, resources, executions, sandbox, threads, evaluation, dependencies, isLoading } =
    useTaskDetails(runState, taskId);

  const generationTurns = runState?.generationTurns ?? [];

  if (!taskId) {
    return (
      <div
        className="flex h-full min-h-[72vh] items-center justify-center rounded-3xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
        data-testid="workspace-empty"
      >
        Select a task from the graph to open the focused task workspace.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex h-full min-h-[72vh] items-center justify-center rounded-3xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400"
        data-testid="workspace-loading"
      >
        Loading task workspace...
      </div>
    );
  }

  if (!task || error) {
    return (
      <div
        className="flex h-full min-h-[72vh] items-center justify-center rounded-3xl border border-red-200 bg-white p-8 text-center text-sm text-red-600 dark:border-red-900 dark:bg-gray-900 dark:text-red-400"
        data-testid="workspace-error"
      >
        {error ?? "Task not found"}
      </div>
    );
  }

  const primarySection =
    resources.length > 0
      ? "outputs"
      : evaluation
        ? "evaluation"
        : threads.length > 0
          ? "communication"
          : sandbox
            ? "sandbox"
            : "overview";

  const started = formatTaskWallTimestamp(task.startedAt);
  const ended = formatTaskWallTimestamp(task.completedAt);

  return (
    <div className="flex h-full min-h-[72vh] flex-col gap-4 xl:min-h-0" data-testid="task-workspace">
      <header
        className="shrink-0 rounded-3xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900"
        data-testid="workspace-header"
      >
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">{task.name}</h2>
          <StatusBadge status={task.status} />
          {onClearSelection && (
            <button
              type="button"
              onClick={onClearSelection}
              className="ml-auto rounded-full border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:bg-gray-800"
              data-testid="workspace-close"
            >
              Back to graph
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm text-gray-500 dark:text-gray-400">
          <span>Worker: {task.assignedWorkerName ?? "—"}</span>
          <span>Level: {task.level}</span>
          <span>Leaf task: {task.isLeaf ? "yes" : "no"}</span>
          <span>Attempts: {executions.length || 0}</span>
          <span>Outputs: {resources.length}</span>
          <span className="tabular-nums">
            Started:{" "}
            {started.dateTime ? (
              <time
                dateTime={started.dateTime}
                title={started.dateTime}
                className="text-gray-700 dark:text-gray-300"
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
                className="text-gray-700 dark:text-gray-300"
              >
                {ended.text}
              </time>
            ) : (
              ended.text
            )}
          </span>
        </div>
        {task.description && (
          <p className="mt-4 text-sm leading-6 text-gray-600 dark:text-gray-300">{task.description}</p>
        )}
      </header>

      <div className="min-h-0 space-y-4 overflow-y-auto pr-1" data-testid="workspace-scroll-region">
        <WorkspaceSection testId="workspace-transitions" title="State transitions">
          <TaskTransitionLog task={task} onJumpToSequence={onJumpToSequence} />
        </WorkspaceSection>

        <WorkspaceSection testId="workspace-generations" title="Generations">
          <GenerationTracePanel turns={generationTurns} runId={runState?.id} />
        </WorkspaceSection>

        <div data-testid="workspace-primary">
          {primarySection === "outputs" && (
            <WorkspaceSection testId="workspace-outputs" title="Outputs">
              <ResourcePanel resources={resources} />
            </WorkspaceSection>
          )}
          {primarySection === "evaluation" && (
            <WorkspaceSection testId="workspace-evaluation" title="Evaluation">
              <EvaluationPanel evaluation={evaluation} />
            </WorkspaceSection>
          )}
          {primarySection === "communication" && (
            <WorkspaceSection testId="workspace-communication" title="Communication">
              <CommunicationPanel threads={threads} />
            </WorkspaceSection>
          )}
          {primarySection === "sandbox" && (
            <WorkspaceSection testId="workspace-sandbox" title="Sandbox">
              <SandboxPanel sandbox={sandbox} />
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

        <div className="grid gap-4 xl:grid-cols-2">
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
            {executions.length === 0 ? (
              <EmptySection message="No execution attempts recorded yet." />
            ) : (
              <div className="space-y-3">
                {executions.map((execution) => (
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
              <CommunicationPanel threads={threads} />
            </WorkspaceSection>
          )}

          {primarySection !== "outputs" && (
            <WorkspaceSection testId="workspace-outputs" title="Outputs">
              <ResourcePanel resources={resources} />
            </WorkspaceSection>
          )}

          {primarySection !== "evaluation" && (
            <WorkspaceSection testId="workspace-evaluation" title="Evaluation">
              <EvaluationPanel evaluation={evaluation} />
            </WorkspaceSection>
          )}

          {primarySection !== "sandbox" && (
            <WorkspaceSection testId="workspace-sandbox" title="Sandbox">
              <SandboxPanel sandbox={sandbox} />
            </WorkspaceSection>
          )}

        </div>
      </div>
    </div>
  );
}
