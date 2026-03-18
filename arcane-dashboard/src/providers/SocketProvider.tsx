"use client";

/**
 * SocketProvider - React context for Socket.io client connection.
 *
 * Provides a persistent Socket.io connection to the dashboard server.
 * Handles connection, reconnection, and cleanup automatically.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import {
  ServerToClientEvents,
  ClientToServerEvents,
} from "@/lib/types";

type TypedSocket = Socket<ServerToClientEvents, ClientToServerEvents>;

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

interface SocketContextValue {
  socket: TypedSocket | null;
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  connectionError: string | null;
  reconnect: () => void;
  subscribe: (runId: string) => void;
  unsubscribe: (runId: string) => void;
}

const SocketContext = createContext<SocketContextValue | null>(null);

interface SocketProviderProps {
  children: React.ReactNode;
}

export function SocketProvider({ children }: SocketProviderProps) {
  const [socket, setSocket] = useState<TypedSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const createSocket = useCallback(() => {
    // Connect to the Socket.io server (same origin)
    const socketInstance: TypedSocket = io({
      // Auto-detect URL from window.location
      path: "/socket.io",
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    socketInstance.on("connect", () => {
      console.log("[Socket.io] Connected:", socketInstance.id);
      setIsConnected(true);
      setConnectionStatus("connected");
      setConnectionError(null);
    });

    socketInstance.on("disconnect", (reason) => {
      console.log("[Socket.io] Disconnected:", reason);
      setIsConnected(false);
      setConnectionStatus("disconnected");
      if (reason === "io server disconnect") {
        setConnectionError("Server disconnected the connection");
      } else if (reason === "transport close") {
        setConnectionError("Connection lost - attempting to reconnect...");
      }
    });

    socketInstance.on("connect_error", (error) => {
      console.error("[Socket.io] Connection error:", error.message);
      setConnectionStatus("error");
      setConnectionError(error.message || "Failed to connect to server");
    });

    socketInstance.io.on("reconnect", (attempt) => {
      console.log("[Socket.io] Reconnected after", attempt, "attempts");
      setConnectionError(null);
    });

    socketInstance.io.on("reconnect_attempt", (attempt) => {
      console.log("[Socket.io] Reconnection attempt", attempt);
      setConnectionStatus("connecting");
      setConnectionError(`Reconnecting... (attempt ${attempt})`);
    });

    socketInstance.io.on("reconnect_failed", () => {
      console.error("[Socket.io] Reconnection failed");
      setConnectionStatus("error");
      setConnectionError("Failed to reconnect after multiple attempts");
    });

    return socketInstance;
  }, []);

  useEffect(() => {
    const socketInstance = createSocket();
    setSocket(socketInstance);

    // Cleanup on unmount
    return () => {
      socketInstance.disconnect();
    };
  }, [createSocket]);

  const reconnect = useCallback(() => {
    if (socket) {
      setConnectionStatus("connecting");
      setConnectionError(null);
      socket.connect();
    }
  }, [socket]);

  const subscribe = useCallback((runId: string) => {
    if (socket?.connected) {
      socket.emit("subscribe", runId);
    }
  }, [socket]);

  const unsubscribe = useCallback((runId: string) => {
    if (socket?.connected) {
      socket.emit("unsubscribe", runId);
    }
  }, [socket]);

  return (
    <SocketContext.Provider 
      value={{ 
        socket, 
        isConnected, 
        connectionStatus, 
        connectionError, 
        reconnect, 
        subscribe, 
        unsubscribe 
      }}
    >
      {children}
    </SocketContext.Provider>
  );
}

/**
 * Hook to access the Socket.io connection from the provider.
 */
export function useSocket(): SocketContextValue {
  const context = useContext(SocketContext);
  if (!context) {
    throw new Error("useSocket must be used within a SocketProvider");
  }
  return context;
}
