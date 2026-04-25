/**
 * Socket.io Server Setup
 *
 * Manages WebSocket connections and room-based subscriptions.
 * Clients subscribe to specific run IDs to receive updates for those runs only.
 */

import { Server as HttpServer } from "http";
import { Server as SocketServer, Socket } from "socket.io";
import { config } from "../config";
import { store } from "../state/store";
import { serializeRunState } from "../runState";
import {
  ContextEventState,
  ServerToClientEvents,
  ClientToServerEvents,
  DashboardCohortUpdatedData,
  DashboardTaskEvaluationUpdatedData,
  DashboardThreadMessageCreatedData,
  ResourceState,
  SandboxState,
  SandboxCommandState,
  TaskStatus,
} from "../types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";

// Typed Socket.io server
type TypedServer = SocketServer<ClientToServerEvents, ServerToClientEvents>;
type TypedSocket = Socket<ClientToServerEvents, ServerToClientEvents>;

// Extend global to store Socket.io instance across module loads
// This is necessary because Next.js API routes may load modules in different contexts
declare global {
  // eslint-disable-next-line no-var
  var __socketIO: TypedServer | null;
}

// Use global to persist io instance across module reloads (hot-reload, API routes, etc.)
// This ensures the same io instance is used everywhere in the Node.js process
function getIO(): TypedServer | null {
  return global.__socketIO ?? null;
}

function setIO(server: TypedServer): void {
  global.__socketIO = server;
}

/**
 * Initialize the Socket.io server with the HTTP server.
 * Call this once when the server starts.
 */
export function initSocketServer(httpServer: HttpServer): TypedServer {
  const io = new SocketServer<ClientToServerEvents, ServerToClientEvents>(
    httpServer,
    {
      cors: {
        origin: config.socketCorsOrigin,
        methods: ["GET", "POST"],
      },
      // Ping interval for connection health
      pingInterval: 25000,
      pingTimeout: 20000,
    }
  );

  // Store in global so it's accessible from API routes / Inngest functions
  setIO(io);

  io.on("connection", (socket: TypedSocket) => {
    console.log(`[Socket.io] Client connected: ${socket.id}`);

    // Debug: log all incoming events
    socket.onAny((eventName, ...args) => {
      console.log(`[Socket.io DEBUG] ${socket.id} emitted event: ${eventName}`, args.length > 0 ? JSON.stringify(args).substring(0, 100) : '');
    });

    // Send current runs to newly connected client
    socket.on("request:runs", () => {
      console.log(`[Socket.io] Client ${socket.id} requested runs sync`);
      const runs = store.getAllRuns();
      console.log(`[Socket.io] Sending ${runs.length} runs to client`);
      socket.emit("sync:runs", runs.map(r => ({
        runId: r.id,
        name: r.name,
        status: r.status,
        startedAt: r.startedAt,
        completedAt: r.completedAt,
        durationSeconds: r.durationSeconds,
        finalScore: r.finalScore,
        error: r.error,
      })));
    });

    // Request full state for a specific run (for run detail page)
    socket.on("request:run", (runId: string) => {
      console.log(`[Socket.io] Client ${socket.id} requested full state for run ${runId}`);
      
      // Debug: log all runs in store
      const allRuns = store.getAllRuns();
      console.log(`[Socket.io] Store contains ${allRuns.length} runs:`, allRuns.map(r => r.id));
      
      const run = store.getRun(runId);
      if (run) {
        console.log(`[Socket.io] Found run! Sending full state (${run.tasks.size} tasks, status: ${run.status})`);
        socket.emit("sync:run", serializeRunState(run));
      } else {
        console.log(`[Socket.io] Run ${runId} NOT FOUND in store. Available runs: ${allRuns.map(r => r.id.substring(0, 8)).join(', ') || 'none'}`);
        socket.emit("sync:run", null);
      }
    });

    // Client subscribes to a run's updates
    socket.on("subscribe", (runId: string) => {
      const room = `run:${runId}`;
      socket.join(room);
      console.log(`[Socket.io] ${socket.id} subscribed to ${room}`);
    });

    // Client unsubscribes from a run's updates
    socket.on("unsubscribe", (runId: string) => {
      const room = `run:${runId}`;
      socket.leave(room);
      console.log(`[Socket.io] ${socket.id} unsubscribed from ${room}`);
    });

    socket.on("disconnect", (reason) => {
      console.log(`[Socket.io] Client disconnected: ${socket.id} (${reason})`);
    });
  });

  console.log("[Socket.io] Server initialized and stored in global");
  return io;
}

/**
 * Get the Socket.io server instance.
 * Returns null if not initialized.
 */
export function getSocketServer(): TypedServer | null {
  return getIO();
}

// =============================================================================
// Broadcast Functions
// =============================================================================

/**
 * Broadcast a new run started to all connected clients.
 */
export function broadcastRunStarted(runId: string, name: string): void {
  const io = getIO();
  console.log(`[Socket.io] broadcastRunStarted called - io is ${io ? 'initialized' : 'NULL'}, runId: ${runId}, name: ${name}`);
  if (io) {
    const socketsCount = io.sockets.sockets.size;
    console.log(`[Socket.io] Broadcasting run:started to ${socketsCount} connected clients`);
    io.emit("run:started", { runId, name });
  } else {
    console.warn("[Socket.io] WARNING: Cannot broadcast run:started - io is null! Check that initSocketServer was called.");
  }
}

export function broadcastCohortUpdated(data: DashboardCohortUpdatedData): void {
  const io = getIO();
  io?.emit("cohort:updated", data);
}

/**
 * Broadcast run completed to subscribers of that run.
 */
export function broadcastRunCompleted(
  runId: string,
  status: "completed" | "failed",
  completedAt: string,
  durationSeconds: number,
  finalScore: number | null,
  error: string | null
): void {
  const io = getIO();
  // Broadcast to all clients (not just room subscribers) so the run list updates
  io?.emit("run:completed", {
    runId,
    status,
    completedAt,
    durationSeconds,
    finalScore,
    error,
  });
}

/**
 * Broadcast task status change to subscribers of that run.
 */
export function broadcastTaskStatus(
  runId: string,
  taskId: string,
  status: TaskStatus,
  timestamp: string,
  assignedWorkerId: string | null,
  assignedWorkerName: string | null
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("task:status", {
    runId,
    taskId,
    status,
    timestamp,
    assignedWorkerId,
    assignedWorkerName,
  });
}

/**
 * Broadcast new resource to subscribers of that run.
 */
export function broadcastResourceNew(
  runId: string,
  resource: ResourceState
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("resource:new", { runId, resource });
}

/**
 * Broadcast sandbox created to subscribers of that run.
 */
export function broadcastSandboxCreated(
  runId: string,
  sandbox: SandboxState
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("sandbox:created", { runId, sandbox });
}

/**
 * Broadcast sandbox command to subscribers of that run.
 */
export function broadcastSandboxCommand(
  runId: string,
  taskId: string,
  command: SandboxCommandState
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("sandbox:command", { runId, taskId, command });
}

/**
 * Broadcast sandbox closed to subscribers of that run.
 */
export function broadcastSandboxClosed(
  runId: string,
  taskId: string,
  reason: string
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("sandbox:closed", { runId, taskId, reason });
}

export function broadcastThreadMessage(
  data: DashboardThreadMessageCreatedData
): void {
  const io = getIO();
  io?.to(`run:${data.run_id}`).emit("thread:message", data);
}

export function broadcastTaskEvaluation(
  data: DashboardTaskEvaluationUpdatedData
): void {
  const io = getIO();
  io?.to(`run:${data.run_id}`).emit("task:evaluation", data);
}

export function broadcastGraphMutation(
  runId: string,
  mutation: DashboardGraphMutationData,
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("graph:mutation", { runId, mutation });
}

export function broadcastContextEvent(
  runId: string,
  taskNodeId: string,
  event: ContextEventState,
): void {
  const io = getIO();
  io?.to(`run:${runId}`).emit("context:event", { runId, taskNodeId, event });
}
