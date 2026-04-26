import type { ContextEventPayload } from "@/lib/contracts/contextEvents";
import { ContextEventCard } from "./ContextEventCard";

interface Props {
  payload: Extract<ContextEventPayload, { event_type: "tool_result" }>;
}

export function ToolResultEvent({ payload }: Props) {
  return (
    <ContextEventCard
      tone={payload.is_error ? "red" : "green"}
      title={payload.is_error ? "Tool error" : "Tool result"}
      badge={payload.tool_name}
      subtitle={payload.tool_call_id}
      payloadLabel="Result"
      payload={payload.result}
    />
  );
}
