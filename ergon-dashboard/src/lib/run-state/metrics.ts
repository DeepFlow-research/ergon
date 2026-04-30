import { TaskStatus, type TaskState, type WorkflowRunState } from "@/lib/types";

export function recalculateTaskMetrics(tasks: Map<string, TaskState>): Pick<
  WorkflowRunState,
  "completedTasks" | "runningTasks" | "failedTasks" | "cancelledTasks"
> {
  let completedTasks = 0;
  let runningTasks = 0;
  let failedTasks = 0;
  let cancelledTasks = 0;

  for (const task of tasks.values()) {
    if (!task.isLeaf) continue;
    if (task.status === TaskStatus.COMPLETED) completedTasks += 1;
    if (task.status === TaskStatus.RUNNING) runningTasks += 1;
    if (task.status === TaskStatus.FAILED) failedTasks += 1;
    if (task.status === TaskStatus.CANCELLED) cancelledTasks += 1;
  }

  return { completedTasks, runningTasks, failedTasks, cancelledTasks };
}
