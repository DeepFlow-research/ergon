import { Inngest, EventSchemas } from "inngest";
import type { DashboardEvents } from "@/lib/types";

// Create the Inngest client for the dashboard
// This client subscribes to events emitted by the Python backend
export const inngest = new Inngest({
  id: "ergon-dashboard",
  schemas: new EventSchemas().fromRecord<DashboardEvents>(),
});
