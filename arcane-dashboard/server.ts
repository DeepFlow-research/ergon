/**
 * Custom Next.js Server with Socket.io
 *
 * This server integrates Next.js with Socket.io to enable real-time updates.
 * It handles both HTTP requests (via Next.js) and WebSocket connections (via Socket.io).
 */

import { createServer } from "http";
import { parse } from "url";
import next from "next";
import { config } from "./src/lib/config";
import { initSocketServer } from "./src/lib/socket/server";

const { isDev, hostname, port } = config;

// Create Next.js app
const app = next({ dev: isDev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  // Create HTTP server
  const server = createServer((req, res) => {
    const parsedUrl = parse(req.url!, true);
    handle(req, res, parsedUrl);
  });

  // Initialize Socket.io on the same server
  initSocketServer(server);

  // Start listening
  server.listen(port, () => {
    console.log(
      `> Ready on http://${hostname}:${port} - env: ${config.nodeEnv}`
    );
    console.log(`> Socket.io server ready`);
  });

  // Handle graceful shutdown
  const shutdown = () => {
    console.log("\n> Shutting down...");
    server.close(() => {
      console.log("> Server closed");
      process.exit(0);
    });
  };

  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
});
