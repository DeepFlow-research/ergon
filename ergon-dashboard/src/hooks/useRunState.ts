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
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardThreadMessageCreatedData,
  parseResourceSocketData,
  parseRunCompletedSocketData,
  parseSandboxClosedSocketData,
  parseSandboxCommandSocketData,
  parseSandboxCreatedSocketData,
  parseTaskStatusSocketData,
} from "@/lib/contracts/events";
import type { GraphMutationSocketData } from "@/lib/contracts/events";
import type { RunSandbox, RunSandboxCommand } from "@/lib/contracts/rest";
import {
  ContextEventState,
  TaskStatus,
  SandboxState,
  SandboxCommandState,
  WorkflowRunState,
  SerializedWorkflowRunState,
} from "@/lib/types";
import { compareContextEvents, deserializeRunState } from "@/lib/runState";
import {
  applySandboxClosed,
  applySandboxCommand,
  applySandboxCreated,
  applyTaskStatusChanged,
} from "@/lib/run-state/reducers";
import { useGraphMutations } from "@/features/graph/hooks/useGraphMutations";

interface UseRunStateResult {
  runState: WorkflowRunState | null;
  isLoading: boolean;
  error: string | null;
  isSubscribed: boolean;
}

function normalizeSandboxState(sandbox: RunSandbox): SandboxState {
  return {
    ...sandbox,
    status: sandbox.status as SandboxState["status"],
    template: sandbox.template ?? null,
    closedAt: sandbox.closedAt ?? null,
    closeReason: sandbox.closeReason ?? null,
    commands: (sandbox.commands ?? []).map((command) => ({
      command: command.command,
      stdout: command.stdout ?? null,
      stderr: command.stderr ?? null,
      exitCode: command.exitCode ?? null,
      durationMs: command.durationMs ?? null,
      timestamp: command.timestamp,
    })),
  };
}

function normalizeSandboxCommandState(command: RunSandboxCommand): SandboxCommandState {
  return {
    command: command.command,
    stdout: command.stdout ?? null,
    stderr: command.stderr ?? null,
    exitCode: command.exitCode ?? null,
    durationMs: command.durationMs ?? null,
    timestamp: command.timestamp,
  };
}

export function shouldRequestSocketSnapshot(hasHydratedRunState: boolean): boolean {
  return !hasHydratedRunState;
}

export function useRunState(
  runId: string,
  initialRunState: SerializedWorkflowRunState | null = null,
): UseRunStateResult {
  const { socket, isConnected, subscribe, unsubscribe } = useSocket();
  const [runState, setRunState] = useState<WorkflowRunState | null>(
    initialRunState ? deserializeRunState(initialRunState) : null,
  );
  const [isLoading, setIsLoading] = useState(initialRunState === null);
  const [error, setError] = useState<string | null>(null);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const subscriptionRef = useRef<string | null>(null);
  const hasRunStateRef = useRef(initialRunState !== null);
  const pendingSandboxCommandsRef = useRef<Map<string, SandboxCommandState[]>>(new Map());

  const loadSnapshot = useCallback(async () => {
    try {
      const response = await fetch(`/api/runs/${runId}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to load run (${response.status})`);
      }
      const data = (await response.json()) as unknown;
      setRunState(deserializeRunState(data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    } finally {
      setIsLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    hasRunStateRef.current = runState !== null;
  }, [runState]);

  useEffect(() => {
    if (initialRunState) {
      setRunState(deserializeRunState(initialRunState));
      setIsLoading(false);
      setError(null);
      return;
    }
    setRunState(null);
    setIsLoading(true);
    void loadSnapshot();
  }, [initialRunState, loadSnapshot]);

  // Handle task status updates
  const handleTaskStatus = useCallback(
    (payload: unknown) => {
      const data = parseTaskStatusSocketData(payload);
      const status = data.status as TaskStatus;
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;
        return applyTaskStatusChanged(prev, {
          runId: data.runId,
          taskId: data.taskId,
          status,
          timestamp: data.timestamp,
          assignedWorkerId: data.assignedWorkerId,
          assignedWorkerSlug: data.assignedWorkerSlug,
        });
      });
    },
    [runId]
  );

  // Handle new resource
  const handleResourceNew = useCallback(
    (payload: unknown) => {
      const data = parseResourceSocketData(payload);
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
    (payload: unknown) => {
      const data = parseSandboxCreatedSocketData(payload);
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const newSandboxesByTask = new Map(prev.sandboxesByTask);
        const taskId = data.sandbox.taskId;
        const pendingCommands = pendingSandboxCommandsRef.current.get(taskId) ?? [];
        pendingSandboxCommandsRef.current.delete(taskId);

        return applySandboxCreated(
          { ...prev, sandboxesByTask: newSandboxesByTask },
          normalizeSandboxState(data.sandbox),
          pendingCommands,
        );
      });
    },
    [runId]
  );

  // Handle sandbox command
  const handleSandboxCommand = useCallback(
    (payload: unknown) => {
      const data = parseSandboxCommandSocketData(payload);
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const command = normalizeSandboxCommandState(data.command);
        if (!prev.sandboxesByTask.has(data.taskId)) {
          const pendingCommands = pendingSandboxCommandsRef.current.get(data.taskId) ?? [];
          pendingSandboxCommandsRef.current.set(data.taskId, [...pendingCommands, command]);
          return prev;
        }

        return applySandboxCommand(prev, data.taskId, command);
      });
    },
    [runId]
  );

  // Handle sandbox closed
  const handleSandboxClosed = useCallback(
    (payload: unknown) => {
      const data = parseSandboxClosedSocketData(payload);
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        return applySandboxClosed(prev, data.taskId, data.reason, data.timestamp);
      });
    },
    [runId]
  );

  // Handle run completed
  const handleRunCompleted = useCallback(
    (payload: unknown) => {
      const data = parseRunCompletedSocketData(payload);
      if (data.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        return {
          ...prev,
          status: data.status,
          completedAt: data.completedAt,
          durationSeconds: data.durationSeconds,
          finalScore: data.finalScore,
          error: data.error,
        };
      });
    },
    [runId]
  );

  const handleThreadMessage = useCallback(
    (payload: unknown) => {
      const data = parseDashboardThreadMessageCreatedData(payload);
      if (data.run_id !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const existingIndex = prev.threads.findIndex((thread) => thread.id === data.thread.id);
        const nextThreads = [...prev.threads];
        if (existingIndex >= 0) {
          nextThreads[existingIndex] = data.thread;
        } else {
          nextThreads.push(data.thread);
        }

        nextThreads.sort((a, b) => a.updatedAt.localeCompare(b.updatedAt));
        return {
          ...prev,
          threads: nextThreads,
        };
      });
    },
    [runId]
  );

  const handleContextEvent = useCallback(
    (payload: { runId: string; taskNodeId: string; event: ContextEventState }) => {
      if (payload.runId !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;
        const nextEvents = new Map(prev.contextEventsByTask);
        const events = nextEvents.get(payload.taskNodeId) ?? [];
        if (events.some((event) => event.id === payload.event.id)) {
          return prev;
        }
        nextEvents.set(
          payload.taskNodeId,
          [...events, payload.event].sort(compareContextEvents),
        );
        return {
          ...prev,
          contextEventsByTask: nextEvents,
        };
      });
    },
    [runId]
  );

  const handleTaskEvaluation = useCallback(
    (payload: unknown) => {
      const data = parseDashboardTaskEvaluationUpdatedData(payload);
      if (data.run_id !== runId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        const nextEvaluations = new Map(prev.evaluationsByTask);
        nextEvaluations.set(data.task_id ?? "__run__", data.evaluation);
        return {
          ...prev,
          evaluationsByTask: nextEvaluations,
        };
      });
    },
    [runId]
  );

  const { handleGraphMutation } = useGraphMutations(setRunState);

  const handleGraphMutationSocket = useCallback(
    (data: GraphMutationSocketData) => {
      if (data.runId !== runId) return;
      handleGraphMutation(data.mutation);
    },
    [runId, handleGraphMutation],
  );

  // Handle full run state sync (for initial load / completed runs)
  const handleSyncRun = useCallback(
    (data: SerializedWorkflowRunState | null) => {
      console.log(
        "[useRunState] Received sync:run",
        data ? `(${Object.keys(data.tasks ?? {}).length} tasks)` : "(null)",
      );
      
      if (!data) {
        setIsLoading(false);
        setError((prev) =>
          runState
            ? prev
            : "Live dashboard state is unavailable. Showing persisted snapshot only when possible."
        );
        return;
      }

      setRunState(deserializeRunState(data));
      setIsLoading(false);
      setError(null);
    },
    [runState]
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
      setIsLoading((prev) => (hasRunStateRef.current ? false : prev));

      if (shouldRequestSocketSnapshot(hasRunStateRef.current)) {
        // Request full run state only when REST/SSR did not hydrate us.
        console.log("[useRunState] Requesting full state for run", runId, "socket.connected:", socket.connected);
        socket.emit("request:run", runId);

        // Set up a retry in case the first request is lost
        retryTimeout = setTimeout(() => {
          if (socket.connected && shouldRequestSocketSnapshot(hasRunStateRef.current)) {
            console.log("[useRunState] Retrying request:run for", runId);
            socket.emit("request:run", runId);
          }
        }, 1000);
      } else {
        console.log("[useRunState] Skipping full socket state request; REST/SSR snapshot is already loaded", runId);
      }
    }

    // Set up event listeners
    socket.on("sync:run", handleSyncRun);
    socket.on("task:status", handleTaskStatus);
    socket.on("resource:new", handleResourceNew);
    socket.on("sandbox:created", handleSandboxCreated);
    socket.on("sandbox:command", handleSandboxCommand);
    socket.on("sandbox:closed", handleSandboxClosed);
    socket.on("run:completed", handleRunCompleted);
    socket.on("thread:message", handleThreadMessage);
    socket.on("task:evaluation", handleTaskEvaluation);
    socket.on("context:event", handleContextEvent);
    socket.on("graph:mutation", handleGraphMutationSocket);

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      socket.off("sync:run", handleSyncRun);
      socket.off("task:status", handleTaskStatus);
      socket.off("resource:new", handleResourceNew);
      socket.off("sandbox:created", handleSandboxCreated);
      socket.off("sandbox:command", handleSandboxCommand);
      socket.off("sandbox:closed", handleSandboxClosed);
      socket.off("run:completed", handleRunCompleted);
      socket.off("thread:message", handleThreadMessage);
      socket.off("task:evaluation", handleTaskEvaluation);
      socket.off("context:event", handleContextEvent);
      socket.off("graph:mutation", handleGraphMutationSocket);
    };
  }, [
    socket,
    isConnected,
    runId,
    subscribe,
    unsubscribe,
    handleSyncRun,
    handleTaskStatus,
    handleResourceNew,
    handleSandboxCreated,
    handleSandboxCommand,
    handleSandboxClosed,
    handleRunCompleted,
    handleThreadMessage,
    handleTaskEvaluation,
    handleContextEvent,
    handleGraphMutationSocket,
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

  // Handle connection errors — only block the UI when we have no data at all.
  // If runState was loaded via REST, socket disconnect is non-fatal.
  useEffect(() => {
    if (!isConnected && socket && !hasRunStateRef.current) {
      setError((prev) => prev ?? "Disconnected from server");
    }
  }, [isConnected, socket]);

  return {
    runState,
    isLoading,
    error,
    isSubscribed,
  };
}
