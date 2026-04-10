import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import { functions } from "@/inngest/functions";

// Serve the Inngest endpoint for the dashboard
// This receives events from the Inngest dev server
export const { GET, POST, PUT } = serve({
  client: inngest,
  functions,
});
