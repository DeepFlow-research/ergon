"use client";

/**
 * useRunState - Hook for managing a single workflow run's state.
 *
 * Subscribes to a specific run's updates and maintains the full
 * WorkflowRunState for that run, including tasks, actions, resources, etc.
 * 
 * On subscription, requests the full run state from the server to hydrate
 * existing data (important for completed runs or page refreshes).
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useSocket } from "@/hooks/useSocket";
import {
  TaskStatus,
  TaskState,
  ActionState,
  ResourceState,
  SandboxState,
  SandboxCommandState,
  WorkflowRunState,
  SerializedWorkflowRunState,
} from "@/lib/types";

interface UseRunStateResult {
  runState: WorkflowRunState | null;
  isLoading: boolean;
  error: string | null;
  isSubscribed: boolean;
}

/**
 * Create an empty WorkflowRunState placeholder.
 */
function createEmptyRunState(runId: string): WorkflowRunState {
  return {
    id: runId,
    experimentId: "",
    name: "Loading...",
    status: "running",
    tasks: new Map(),
    rootTaskId: "",
    actionsByTask: new Map(),
    resourcesByTask: new Map(),
    sandboxesByTask: new Map(),
    startedAt: new Date().toISOString(),
    completedAt: null,
    durationSeconds: null,
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
    finalScore: null,
    error: null,
  };
}

export function useRunState(runId: string): UseRunStateResult {
  const { socket, isConnected, subscribe, unsubscribe } = useSocket();
  const [runState, setRunState] = useState<WorkflowRunState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const subscriptionRef = useRef<string | null>(null);

  // Handle task status updates
  const handleTaskStatus = useCallback(
    (data: {
      runId: string;
      taskId: string;
      status: TaskStatus;
      assignedWorkerId: string | null;
      assignedWorkerName: string | null;
    }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const task = prev.tasks.get(data.taskId);
        if (!task) return prev;

        const updatedTask: TaskState = {
          ...task,
          status: data.status,
          assignedWorkerId: data.assignedWorkerId ?? task.assignedWorkerId,
          assignedWorkerName: data.assignedWorkerName ?? task.assignedWorkerName,
          startedAt:
            data.status === TaskStatus.RUNNING && !task.startedAt
              ? new Date().toISOString()
              : task.startedAt,
          completedAt:
            data.status === TaskStatus.COMPLETED ||
            data.status === TaskStatus.FAILED
              ? new Date().toISOString()
              : task.completedAt,
        };

        const newTasks = new Map(prev.tasks);
        newTasks.set(data.taskId, updatedTask);

        // Recalculate metrics
        let completedTasks = 0;
        let runningTasks = 0;
        let failedTasks = 0;

        for (const t of newTasks.values()) {
          if (!t.isLeaf) continue;
          switch (t.status) {
            case TaskStatus.COMPLETED:
              completedTasks++;
              break;
            case TaskStatus.RUNNING:
              runningTasks++;
              break;
            case TaskStatus.FAILED:
              failedTasks++;
              break;
          }
        }

        return {
          ...prev,
          tasks: newTasks,
          completedTasks,
          runningTasks,
          failedTasks,
        };
      });
    },
    [runId]
  );

  // Handle new action
  const handleActionNew = useCallback(
    (data: { runId: string; action: ActionState }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const taskActions = prev.actionsByTask.get(data.action.taskId) ?? [];
        const newActionsByTask = new Map(prev.actionsByTask);
        newActionsByTask.set(data.action.taskId, [...taskActions, data.action]);

        return { ...prev, actionsByTask: newActionsByTask };
      });
    },
    [runId]
  );

  // Handle action completed
  const handleActionCompleted = useCallback(
    (data: { runId: string; action: ActionState }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const taskActions = prev.actionsByTask.get(data.action.taskId) ?? [];
        const updatedActions = taskActions.map((a) =>
          a.id === data.action.id ? data.action : a
        );

        const newActionsByTask = new Map(prev.actionsByTask);
        newActionsByTask.set(data.action.taskId, updatedActions);

        return { ...prev, actionsByTask: newActionsByTask };
      });
    },
    [runId]
  );

  // Handle new resource
  const handleResourceNew = useCallback(
    (data: { runId: string; resource: ResourceState }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const taskResources =
          prev.resourcesByTask.get(data.resource.taskId) ?? [];
        const newResourcesByTask = new Map(prev.resourcesByTask);
        newResourcesByTask.set(data.resource.taskId, [
          ...taskResources,
          data.resource,
        ]);

        return { ...prev, resourcesByTask: newResourcesByTask };
      });
    },
    [runId]
  );

  // Handle sandbox created
  const handleSandboxCreated = useCallback(
    (data: { runId: string; sandbox: SandboxState }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const newSandboxesByTask = new Map(prev.sandboxesByTask);
        newSandboxesByTask.set(data.sandbox.taskId, data.sandbox);

        return { ...prev, sandboxesByTask: newSandboxesByTask };
      });
    },
    [runId]
  );

  // Handle sandbox command
  const handleSandboxCommand = useCallback(
    (data: { runId: string; taskId: string; command: SandboxCommandState }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const sandbox = prev.sandboxesByTask.get(data.taskId);
        if (!sandbox) return prev;

        const updatedSandbox: SandboxState = {
          ...sandbox,
          commands: [...sandbox.commands, data.command],
        };

        const newSandboxesByTask = new Map(prev.sandboxesByTask);
        newSandboxesByTask.set(data.taskId, updatedSandbox);

        return { ...prev, sandboxesByTask: newSandboxesByTask };
      });
    },
    [runId]
  );

  // Handle sandbox closed
  const handleSandboxClosed = useCallback(
    (data: { runId: string; taskId: string; reason: string }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const sandbox = prev.sandboxesByTask.get(data.taskId);
        if (!sandbox) return prev;

        const updatedSandbox: SandboxState = {
          ...sandbox,
          status: "closed",
          closedAt: new Date().toISOString(),
          closeReason: data.reason,
        };

        const newSandboxesByTask = new Map(prev.sandboxesByTask);
        newSandboxesByTask.set(data.taskId, updatedSandbox);

        return { ...prev, sandboxesByTask: newSandboxesByTask };
      });
    },
    [runId]
  );

  // Handle run completed
  const handleRunCompleted = useCallback(
    (data: {
      runId: string;
      status: "completed" | "failed";
      durationSeconds: number;
      finalScore: number | null;
      error: string | null;
    }) => {
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        return {
          ...prev,
          status: data.status,
          completedAt: new Date().toISOString(),
          durationSeconds: data.durationSeconds,
          finalScore: data.finalScore,
          error: data.error,
        };
      });
    },
    [runId]
  );

  // Handle full run state sync (for initial load / completed runs)
  const handleSyncRun = useCallback(
    (data: SerializedWorkflowRunState | null) => {
      console.log("[useRunState] Received sync:run", data ? `(${data.tasks.length} tasks)` : "(null)");
      
      if (!data) {
        // Run not in store - this happens when viewing old runs after dashboard restart
        setError("Run not found. The dashboard only stores runs from the current session. Try running a new workflow.");
        setIsLoading(false);
        // Keep runState null so error UI shows (error is checked before empty state)
        return;
      }

      // Convert serialized arrays back to Maps
      const runState: WorkflowRunState = {
        id: data.id,
        experimentId: data.experimentId,
        name: data.name,
        status: data.status,
        tasks: new Map(data.tasks),
        rootTaskId: data.rootTaskId,
        actionsByTask: new Map(data.actionsByTask),
        resourcesByTask: new Map(data.resourcesByTask),
        sandboxesByTask: new Map(data.sandboxesByTask),
        startedAt: data.startedAt,
        completedAt: data.completedAt,
        durationSeconds: data.durationSeconds,
        totalTasks: data.totalTasks,
        totalLeafTasks: data.totalLeafTasks,
        completedTasks: data.completedTasks,
        runningTasks: data.runningTasks,
        failedTasks: data.failedTasks,
        finalScore: data.finalScore,
        error: data.error,
      };

      setRunState(runState);
      setIsLoading(false);
      setError(null);
    },
    []
  );

  // Subscribe to run updates
  useEffect(() => {
    if (!socket || !isConnected) {
      console.log("[useRunState] Socket not ready - socket:", !!socket, "isConnected:", isConnected);
      return;
    }

    let retryTimeout: ReturnType<typeof setTimeout> | null = null;

    // Only subscribe if we haven't already for this runId
    if (subscriptionRef.current !== runId) {
      // Unsubscribe from previous run if any
      if (subscriptionRef.current) {
        unsubscribe(subscriptionRef.current);
      }

      // Subscribe to new run
      console.log("[useRunState] Subscribing to run", runId);
      subscribe(runId);
      subscriptionRef.current = runId;
      setIsSubscribed(true);
      setIsLoading(true);

      // Request full run state from server
      console.log("[useRunState] Requesting full state for run", runId, "socket.connected:", socket.connected);
      socket.emit("request:run", runId);
      
      // Set up a retry in case the first request is lost
      retryTimeout = setTimeout(() => {
        if (socket.connected) {
          console.log("[useRunState] Retrying request:run for", runId);
          socket.emit("request:run", runId);
        }
      }, 1000);
    }

    // Set up event listeners
    socket.on("sync:run", handleSyncRun);
    socket.on("task:status", handleTaskStatus);
    socket.on("action:new", handleActionNew);
    socket.on("action:completed", handleActionCompleted);
    socket.on("resource:new", handleResourceNew);
    socket.on("sandbox:created", handleSandboxCreated);
    socket.on("sandbox:command", handleSandboxCommand);
    socket.on("sandbox:closed", handleSandboxClosed);
    socket.on("run:completed", handleRunCompleted);

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      socket.off("sync:run", handleSyncRun);
      socket.off("task:status", handleTaskStatus);
      socket.off("action:new", handleActionNew);
      socket.off("action:completed", handleActionCompleted);
      socket.off("resource:new", handleResourceNew);
      socket.off("sandbox:created", handleSandboxCreated);
      socket.off("sandbox:command", handleSandboxCommand);
      socket.off("sandbox:closed", handleSandboxClosed);
      socket.off("run:completed", handleRunCompleted);
    };
  }, [
    socket,
    isConnected,
    runId,
    subscribe,
    unsubscribe,
    handleSyncRun,
    handleTaskStatus,
    handleActionNew,
    handleActionCompleted,
    handleResourceNew,
    handleSandboxCreated,
    handleSandboxCommand,
    handleSandboxClosed,
    handleRunCompleted,
  ]);

  // Unsubscribe on unmount
  useEffect(() => {
    return () => {
      if (subscriptionRef.current) {
        unsubscribe(subscriptionRef.current);
        subscriptionRef.current = null;
      }
    };
  }, [unsubscribe]);

  // Handle connection errors
  useEffect(() => {
    if (!isConnected && socket) {
      setError("Disconnected from server");
    } else {
      setError(null);
    }
  }, [isConnected, socket]);

  return {
    runState,
    isLoading,
    error,
    isSubscribed,
  };
}
