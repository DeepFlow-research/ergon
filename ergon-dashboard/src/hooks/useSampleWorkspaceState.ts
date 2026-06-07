"use client";

/**
 * useSampleWorkspaceState - Hook for managing a single sample's state.
 *
 * Subscribes to a specific sample's updates and maintains the full
 * SampleWorkspaceState for that sample, including tasks, actions, resources, etc.
 * 
 * On subscription, requests the full sample state from the server to hydrate
 * existing data (important for completed samples or page refreshes).
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useSocket } from "@/hooks/useSocket";
import {
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardThreadMessageCreatedData,
  parseResourceSocketData,
  parseSampleCompletedSocketData,
  parseSandboxClosedSocketData,
  parseSandboxCommandSocketData,
  parseSandboxCreatedSocketData,
  parseTaskStatusSocketData,
} from "@/lib/contracts/events";
import type { SampleRuntimeEventSocketData } from "@/lib/contracts/events";
import type { SampleSandbox, SampleSandboxCommand } from "@/lib/contracts/rest";
import {
  ContextEventState,
  TaskStatus,
  SandboxState,
  SandboxCommandState,
  SampleWorkspaceState,
  SerializedSampleWorkspaceState,
} from "@/lib/types";
import { compareContextEvents, deserializeSampleState } from "@/lib/sampleState";
import {
  applySandboxClosed,
  applySandboxCommand,
  applySandboxCreated,
  applyTaskStatusChanged,
} from "@/lib/sample-state/reducers";
import { useGraphMutations } from "@/features/graph/hooks/useGraphMutations";

interface UseSampleWorkspaceStateResult {
  runState: SampleWorkspaceState | null;
  isLoading: boolean;
  error: string | null;
  isSubscribed: boolean;
}

function normalizeSandboxState(sandbox: SampleSandbox): SandboxState {
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

function normalizeSandboxCommandState(command: SampleSandboxCommand): SandboxCommandState {
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

export function useSampleWorkspaceState(
  sampleId: string,
  initialRunState: SerializedSampleWorkspaceState | null = null,
): UseSampleWorkspaceStateResult {
  const { socket, isConnected, subscribe, unsubscribe } = useSocket();
  const [runState, setRunState] = useState<SampleWorkspaceState | null>(
    initialRunState ? deserializeSampleState(initialRunState) : null,
  );
  const [isLoading, setIsLoading] = useState(initialRunState === null);
  const [error, setError] = useState<string | null>(null);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const subscriptionRef = useRef<string | null>(null);
  const hasRunStateRef = useRef(initialRunState !== null);
  const pendingSandboxCommandsRef = useRef<Map<string, SandboxCommandState[]>>(new Map());

  const loadSnapshot = useCallback(async () => {
    try {
      const response = await fetch(`/api/samples/${sampleId}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to load run (${response.status})`);
      }
      const data = (await response.json()) as unknown;
      setRunState(deserializeSampleState(data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    } finally {
      setIsLoading(false);
    }
  }, [sampleId]);

  useEffect(() => {
    hasRunStateRef.current = runState !== null;
  }, [runState]);

  useEffect(() => {
    if (initialRunState) {
      setRunState(deserializeSampleState(initialRunState));
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
      if (data.sampleId !== sampleId) return;

      setRunState((prev) => {
        if (!prev) return prev;
        return applyTaskStatusChanged(prev, {
          sampleId: data.sampleId,
          taskId: data.taskId,
          status,
          timestamp: data.timestamp,
          assignedWorkerId: data.assignedWorkerId,
          assignedWorkerSlug: data.assignedWorkerSlug,
        });
      });
    },
    [sampleId]
  );

  // Handle new resource
  const handleResourceNew = useCallback(
    (payload: unknown) => {
      const data = parseResourceSocketData(payload);
      if (data.sampleId !== sampleId) return;

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
    [sampleId]
  );

  // Handle sandbox created
  const handleSandboxCreated = useCallback(
    (payload: unknown) => {
      const data = parseSandboxCreatedSocketData(payload);
      if (data.sampleId !== sampleId) return;

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
    [sampleId]
  );

  // Handle sandbox command
  const handleSandboxCommand = useCallback(
    (payload: unknown) => {
      const data = parseSandboxCommandSocketData(payload);
      if (data.sampleId !== sampleId) return;

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
    [sampleId]
  );

  // Handle sandbox closed
  const handleSandboxClosed = useCallback(
    (payload: unknown) => {
      const data = parseSandboxClosedSocketData(payload);
      if (data.sampleId !== sampleId) return;

      setRunState((prev) => {
        if (!prev) return prev;

        return applySandboxClosed(prev, data.taskId, data.reason, data.timestamp);
      });
    },
    [sampleId]
  );

  // Handle sample completed
  const handleSampleCompleted = useCallback(
    (payload: unknown) => {
      const data = parseSampleCompletedSocketData(payload);
      if (data.sampleId !== sampleId) return;

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
    [sampleId]
  );

  const handleThreadMessage = useCallback(
    (payload: unknown) => {
      const data = parseDashboardThreadMessageCreatedData(payload);
      if (data.sample_id !== sampleId) return;

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
    [sampleId]
  );

  const handleContextEvent = useCallback(
    (payload: { sampleId: string; taskId: string; event: ContextEventState }) => {
      if (payload.sampleId !== sampleId) return;

      setRunState((prev) => {
        if (!prev) return prev;
        const nextEvents = new Map(prev.contextEventsByTask);
        const events = nextEvents.get(payload.taskId) ?? [];
        if (events.some((event) => event.id === payload.event.id)) {
          return prev;
        }
        nextEvents.set(
          payload.taskId,
          [...events, payload.event].sort(compareContextEvents),
        );
        return {
          ...prev,
          contextEventsByTask: nextEvents,
        };
      });
    },
    [sampleId]
  );

  const handleTaskEvaluation = useCallback(
    (payload: unknown) => {
      const data = parseDashboardTaskEvaluationUpdatedData(payload);
      if (data.sample_id !== sampleId) return;

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
    [sampleId]
  );

  const { handleGraphMutation } = useGraphMutations(setRunState);

  const handleGraphMutationSocket = useCallback(
    (data: SampleRuntimeEventSocketData) => {
      if (data.sampleId !== sampleId) return;
      handleGraphMutation(data.mutation);
    },
    [sampleId, handleGraphMutation],
  );

  // Handle full sample state sync (for initial load / completed samples)
  const handleSyncRun = useCallback(
    (data: SerializedSampleWorkspaceState | null) => {
      console.log(
        "[useSampleWorkspaceState] Received sync:sample",
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

      setRunState(deserializeSampleState(data));
      setIsLoading(false);
      setError(null);
    },
    [runState]
  );

  // Subscribe to run updates
  useEffect(() => {
    if (!socket || !isConnected) {
      console.log("[useSampleWorkspaceState] Socket not ready - socket:", !!socket, "isConnected:", isConnected);
      return;
    }

    let retryTimeout: ReturnType<typeof setTimeout> | null = null;

    // Only subscribe if we haven't already for this sampleId
    if (subscriptionRef.current !== sampleId) {
      // Unsubscribe from previous run if any
      if (subscriptionRef.current) {
        unsubscribe(subscriptionRef.current);
      }

      // Subscribe to new run
      console.log("[useSampleWorkspaceState] Subscribing to run", sampleId);
      subscribe(sampleId);
      subscriptionRef.current = sampleId;
      setIsSubscribed(true);
      setIsLoading((prev) => (hasRunStateRef.current ? false : prev));

      if (shouldRequestSocketSnapshot(hasRunStateRef.current)) {
        // Request full sample state only when REST/SSR did not hydrate us.
        console.log("[useSampleWorkspaceState] Requesting full state for run", sampleId, "socket.connected:", socket.connected);
        socket.emit("request:sample", sampleId);

        // Set up a retry in case the first request is lost
        retryTimeout = setTimeout(() => {
          if (socket.connected && shouldRequestSocketSnapshot(hasRunStateRef.current)) {
            console.log("[useSampleWorkspaceState] Retrying request:sample for", sampleId);
            socket.emit("request:sample", sampleId);
          }
        }, 1000);
      } else {
        console.log("[useSampleWorkspaceState] Skipping full socket state request; REST/SSR snapshot is already loaded", sampleId);
      }
    }

    // Set up event listeners
    socket.on("sync:sample", handleSyncRun);
    socket.on("task:status", handleTaskStatus);
    socket.on("resource:new", handleResourceNew);
    socket.on("sandbox:created", handleSandboxCreated);
    socket.on("sandbox:command", handleSandboxCommand);
    socket.on("sandbox:closed", handleSandboxClosed);
    socket.on("sample:completed", handleSampleCompleted);
    socket.on("thread:message", handleThreadMessage);
    socket.on("task:evaluation", handleTaskEvaluation);
    socket.on("context:event", handleContextEvent);
    socket.on("sample:runtime-event", handleGraphMutationSocket);

    return () => {
      if (retryTimeout) clearTimeout(retryTimeout);
      socket.off("sync:sample", handleSyncRun);
      socket.off("task:status", handleTaskStatus);
      socket.off("resource:new", handleResourceNew);
      socket.off("sandbox:created", handleSandboxCreated);
      socket.off("sandbox:command", handleSandboxCommand);
      socket.off("sandbox:closed", handleSandboxClosed);
      socket.off("sample:completed", handleSampleCompleted);
      socket.off("thread:message", handleThreadMessage);
      socket.off("task:evaluation", handleTaskEvaluation);
      socket.off("context:event", handleContextEvent);
      socket.off("sample:runtime-event", handleGraphMutationSocket);
    };
  }, [
    socket,
    isConnected,
    sampleId,
    subscribe,
    unsubscribe,
    handleSyncRun,
    handleTaskStatus,
    handleResourceNew,
    handleSandboxCreated,
    handleSandboxCommand,
    handleSandboxClosed,
    handleSampleCompleted,
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
