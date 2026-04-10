/**
 * Dashboard Configuration
 *
 * Centralized configuration for the dashboard server.
 * Values are read from environment variables with sensible defaults.
 */

export const config = {
  // Server
  nodeEnv: process.env.NODE_ENV || "development",
  isDev: process.env.NODE_ENV !== "production",
  hostname: process.env.HOSTNAME || "0.0.0.0",
  port: parseInt(process.env.PORT || "3000", 10),

  // Inngest
  inngestEventKey: process.env.INNGEST_EVENT_KEY || "dev",
  inngestApiBaseUrl: process.env.INNGEST_API_BASE_URL,

  // Backend API
  arcaneApiBaseUrl: process.env.ARCANE_API_BASE_URL || "http://localhost:9000",

  // Socket.io
  socketCorsOrigin: process.env.SOCKET_CORS_ORIGIN || "*",

  // Testing
  enableTestHarness: process.env.ENABLE_TEST_HARNESS === "1",

  // Store
  maxRunsToKeep: parseInt(process.env.MAX_RUNS_TO_KEEP || "50", 10),
} as const;

export type Config = typeof config;
